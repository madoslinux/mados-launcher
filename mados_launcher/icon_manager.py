"""Icon management: buttons, groups, popovers, animations."""

import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from mados_launcher.config import (
    ICON_SIZE,
    ICON_PADDING,
    TAB_HEIGHT,
    ICON_ZOOM_SIZE,
    ICON_ZOOM_STEP,
    ICON_ZOOM_INTERVAL_MS,
)
from mados_launcher.desktop_entries import launch_application, EntryGroup
from mados_launcher.window_tracker import WindowTracker
from mados_launcher.logger import log


class IconManager:
    """Manages dock icons, groups, popovers, and animations."""

    def __init__(self, icons_box: Gtk.Box, tracker: WindowTracker):
        self._icons_box = icons_box
        self._tracker = tracker
        self._entries = []
        self._grouped = []
        self._icon_buttons = []

        self._zoom_state = {}
        self._bounce_state = {}
        self._active_popover = None

    def set_entries(self, entries, grouped):
        """Set desktop entries to display."""
        self._entries = entries
        self._grouped = grouped
        self.rebuild_icons()

    def rebuild_icons(self):
        """Clear and rebuild all icon buttons."""
        for child in self._icons_box.get_children():
            self._icons_box.remove(child)
        self._icon_buttons.clear()

        for item in self._grouped:
            if isinstance(item, EntryGroup):
                self._build_group_icon(item)
            else:
                self._build_single_icon(item)

    def _build_single_icon(self, entry):
        """Build icon button for a single entry."""
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item_box.set_size_request(48, TAB_HEIGHT)

        align = Gtk.Alignment(xalign=0.5, yalign=0.5, xscale=0, yscale=0)
        align.set_size_request(48, TAB_HEIGHT)

        btn = Gtk.Button()
        btn.set_tooltip_text(entry.name)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_size_request(48, 48)

        image = self._make_icon_image(entry)
        image.set_size_request(ICON_SIZE, ICON_SIZE)
        btn.add(image)
        btn.connect("clicked", self._on_icon_clicked, entry.exec_cmd, entry.terminal)

        btn.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        btn.connect("enter-notify-event", self._on_icon_enter, entry, image)
        btn.connect("leave-notify-event", self._on_icon_leave, entry, image)

        align.add(btn)

        indicator = Gtk.DrawingArea()
        indicator.set_size_request(48, 6)
        indicator.connect("draw", self._on_draw_indicator, entry)

        item_box.pack_start(align, True, True, 0)
        item_box.pack_end(indicator, False, False, 0)

        self._icons_box.pack_start(item_box, False, False, 0)
        self._icon_buttons.append((btn, indicator, entry, align, image))

    def _build_group_icon(self, group):
        """Build icon button for a group - shows popover on click."""
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item_box.set_size_request(48, TAB_HEIGHT)

        align = Gtk.Alignment(xalign=0.5, yalign=0.5, xscale=0, yscale=0)
        align.set_size_request(48, TAB_HEIGHT)

        btn = Gtk.Button()
        btn.set_tooltip_text(f"{group.group_name} ({len(group.entries)})")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_size_request(48, 48)

        image = self._make_icon_image(group.representative)
        image.set_size_request(ICON_SIZE, ICON_SIZE)
        btn.add(image)
        btn.connect("clicked", self._on_group_clicked, group)

        btn.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        btn.connect(
            "enter-notify-event", self._on_icon_enter, group.representative, image
        )
        btn.connect(
            "leave-notify-event", self._on_icon_leave, group.representative, image
        )

        align.add(btn)

        indicator = Gtk.DrawingArea()
        indicator.set_size_request(48, 6)
        indicator.connect("draw", self._on_draw_group_indicator, group)

        item_box.pack_start(align, True, True, 0)
        item_box.pack_end(indicator, False, False, 0)

        self._icons_box.pack_start(item_box, False, False, 0)
        for entry in group.entries:
            self._icon_buttons.append((btn, indicator, entry, align, image))

    def _make_icon_image(self, entry):
        """Create Gtk.Image from entry icon."""
        if entry.pixbuf and isinstance(entry.pixbuf, GdkPixbuf.Pixbuf):
            if (
                entry.pixbuf.get_width() != ICON_SIZE
                or entry.pixbuf.get_height() != ICON_SIZE
            ):
                pixbuf = entry.pixbuf.scale_simple(
                    ICON_SIZE, ICON_SIZE, GdkPixbuf.InterpType.BILINEAR
                )
                return Gtk.Image.new_from_pixbuf(pixbuf)
            return Gtk.Image.new_from_pixbuf(entry.pixbuf)
        else:
            image = Gtk.Image.new_from_icon_name(
                "application-x-executable", Gtk.IconSize.LARGE_TOOLBAR
            )
            image.set_pixel_size(ICON_SIZE)
            return image

    def _on_icon_clicked(self, btn, exec_cmd, terminal):
        """Launch application on click."""
        self._cancel_zoom_animation(btn)
        launch_application(exec_cmd, terminal)
        self._start_bounce_animation(btn)

    def _on_group_clicked(self, btn, group):
        """Show popover with group items."""
        self._dismiss_active_popover()

        popover = Gtk.Popover()
        popover.set_relative_to(btn)
        popover.set_position(Gtk.PositionType.RIGHT)
        popover.connect("closed", self._on_popover_closed)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_margin_start(4)
        vbox.set_margin_end(4)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)

        for entry in group.entries:
            row = Gtk.Button()
            row.set_relief(Gtk.ReliefStyle.NONE)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.set_margin_start(4)
            hbox.set_margin_end(4)
            hbox.set_margin_top(2)
            hbox.set_margin_bottom(2)

            if entry.pixbuf and isinstance(entry.pixbuf, GdkPixbuf.Pixbuf):
                small = ICON_SIZE - 2
                if (
                    entry.pixbuf.get_width() != small
                    or entry.pixbuf.get_height() != small
                ):
                    pixbuf = entry.pixbuf.scale_simple(
                        small, small, GdkPixbuf.InterpType.BILINEAR
                    )
                    icon = Gtk.Image.new_from_pixbuf(pixbuf)
                else:
                    icon = Gtk.Image.new_from_pixbuf(entry.pixbuf)
            else:
                icon = Gtk.Image.new_from_icon_name(
                    "application-x-executable", Gtk.IconSize.MENU
                )
                icon.set_pixel_size(ICON_SIZE - 2)

            hbox.pack_start(icon, False, False, 0)

            label = Gtk.Label(label=entry.name)
            label.set_xalign(0)
            hbox.pack_start(label, True, True, 0)

            if self._tracker.is_running(entry.exec_cmd, entry.filename):
                dot = Gtk.Label(label="\u25cf")
                dot.modify_fg(Gtk.StateFlags.NORMAL, Gdk.color_parse("#88C0D0"))
                hbox.pack_end(dot, False, False, 0)

            row.add(hbox)
            row.connect(
                "clicked",
                self._on_popover_item_clicked,
                popover,
                entry.exec_cmd,
                entry.terminal,
            )
            vbox.pack_start(row, False, False, 0)

        popover.add(vbox)
        popover.show_all()
        self._active_popover = popover

    def _on_popover_item_clicked(self, btn, popover, exec_cmd, terminal):
        """Launch app from popover and close it."""
        popover.popdown()
        self._cancel_zoom_animation(popover.get_relative_to())
        launch_application(exec_cmd, terminal)
        self._start_bounce_animation(popover.get_relative_to())

    def _dismiss_active_popover(self):
        """Close any open popover."""
        if self._active_popover:
            try:
                self._active_popover.popdown()
            except (AttributeError, RuntimeError):
                pass
            self._active_popover = None

    def _on_popover_closed(self, popover):
        """Clear active popover reference."""
        if self._active_popover is popover:
            self._active_popover = None

    def _on_icon_enter(self, btn, event, entry, image):
        """Start zoom-in animation."""
        self._animate_icon_zoom(btn, image, entry, ICON_ZOOM_SIZE)

    def _on_icon_leave(self, btn, event, entry, image):
        """Start zoom-out animation."""
        self._animate_icon_zoom(btn, image, entry, ICON_SIZE)

    def _animate_icon_zoom(self, btn, image, entry, target_size):
        """Animate icon zoom."""
        key = id(btn)
        state = self._zoom_state.get(key)

        if state and state.get("timer"):
            GLib.source_remove(state["timer"])

        current = state["current_size"] if state else ICON_SIZE

        self._zoom_state[key] = {
            "current_size": current,
            "target_size": target_size,
            "entry": entry,
            "btn": btn,
            "image": image,
            "timer": GLib.timeout_add(ICON_ZOOM_INTERVAL_MS, self._zoom_tick, key),
        }

    def _zoom_tick(self, key):
        """Advance zoom animation frame."""
        state = self._zoom_state.get(key)
        if not state:
            return False

        current = state["current_size"]
        target = state["target_size"]

        if current == target:
            state["timer"] = None
            return False

        if current < target:
            new_size = min(current + ICON_ZOOM_STEP, target)
        else:
            new_size = max(current - ICON_ZOOM_STEP, target)

        state["current_size"] = new_size
        self._apply_icon_size(state["image"], new_size, state["entry"])

        if new_size == target:
            state["timer"] = None
            return False
        return True

    def _apply_icon_size(self, image, size, entry):
        """Set icon size."""
        if image is None:
            return
        if entry.pixbuf and isinstance(entry.pixbuf, GdkPixbuf.Pixbuf):
            pixbuf = entry.pixbuf.scale_simple(
                size, size, GdkPixbuf.InterpType.BILINEAR
            )
            image.set_from_pixbuf(pixbuf)
        else:
            image.set_pixel_size(size)

    def _cancel_zoom_animation(self, btn):
        """Cancel zoom animation."""
        key = id(btn)
        state = self._zoom_state.get(key)
        if state and state.get("timer"):
            GLib.source_remove(state["timer"])
            del self._zoom_state[key]

    def _start_bounce_animation(self, btn):
        """Start bounce animation on icon."""
        key = id(btn)
        if key in self._bounce_state:
            return

        align = None
        for item in self._icon_buttons:
            if item[0] == btn:
                align = item[3]
                break

        if not align:
            return

        self._bounce_state[key] = {
            "start_time": GLib.get_monotonic_time(),
            "timer": GLib.timeout_add(16, self._bounce_tick, key),
            "btn": btn,
            "align": align,
        }

    def _bounce_tick(self, key):
        """Advance bounce animation frame."""
        state = self._bounce_state.get(key)
        if not state:
            return False

        elapsed = (GLib.get_monotonic_time() - state["start_time"]) / 1000000.0
        bounce = abs(math.sin(elapsed * math.pi * 2))
        y_offset = bounce * 0.42

        state["align"].set_property("yalign", 0.5 - y_offset)
        return True

    def stop_bounce_animation(self):
        """Stop all bounce animations."""
        for key, state in list(self._bounce_state.items()):
            if state.get("timer"):
                GLib.source_remove(state["timer"])
            if state.get("align"):
                state["align"].set_property("yalign", 0.5)
        self._bounce_state.clear()

    def update_indicators(self):
        """Redraw all indicators."""
        for btn, indicator, entry, align, image in self._icon_buttons:
            indicator.queue_draw()

    def _on_draw_indicator(self, widget, cr, entry):
        """Draw indicator for single entry."""
        running = self._tracker.is_running(entry.exec_cmd, entry.filename)
        urgent = self._tracker.is_urgent(entry.exec_cmd, entry.filename)
        focused = self._tracker.is_focused(entry.exec_cmd, entry.filename)

        if not running:
            return False

        alloc = widget.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2

        if urgent:
            color = "#D08770"
            radius = 3.5
        elif focused:
            color = "#88C0D0"
            radius = 3.5
        else:
            color = "#81A1C1"
            radius = 3.0

        rgb = self._hex_to_rgb(color)
        cr.set_source_rgb(*rgb)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()
        return False

    def _on_draw_group_indicator(self, widget, cr, group):
        """Draw indicator for group."""
        any_running = any(
            self._tracker.is_running(e.exec_cmd, e.filename) for e in group.entries
        )
        any_urgent = any(
            self._tracker.is_urgent(e.exec_cmd, e.filename) for e in group.entries
        )
        any_focused = any(
            self._tracker.is_focused(e.exec_cmd, e.filename) for e in group.entries
        )

        if not any_running:
            return False

        alloc = widget.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2

        if any_urgent:
            color = "#D08770"
            radius = 3.5
        elif any_focused:
            color = "#88C0D0"
            radius = 3.5
        else:
            color = "#81A1C1"
            radius = 3.0

        rgb = self._hex_to_rgb(color)
        cr.set_source_rgb(*rgb)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()
        return False

    def _hex_to_rgb(self, hex_color):
        """Convert hex to RGB."""
        h = hex_color.lstrip("#")
        return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
