"""Single dock instance for one monitor."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk, GLib

from .config import TAB_WIDTH, TAB_HEIGHT
from .dock_renderer import DockRenderer
from .dock_icon import DockIcon
from .desktop_entries import scan_desktop_entries, group_entries
from .window_tracker import WindowTracker
from .logger import log


class DockInstance:
    """Manages a single dock instance for one monitor."""

    def __init__(self, window: Gtk.Window, app, index: int, tracker=None):
        self._window = window
        self._app = app
        self._index = index
        self._expanded = False
        self._button_pressed = False
        self._is_dragging = False
        self._drag_start_y = 0
        self._drag_start_margin = 0
        self._renderer = DockRenderer()
        self._dock_icons = []
        self._tracker = tracker if tracker else WindowTracker()

        self._build_ui()
        self._setup_events()
        self._load_icons()

    def _build_ui(self):
        self._fixed = Gtk.Fixed()
        self._fixed.set_size_request(150, 150)
        self._window.add(self._fixed)

        self._tab_y = (150 - TAB_HEIGHT) // 2
        self._revealer_x = TAB_WIDTH

        # Icons box (same position and height as grip)
        self._icons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._icons_box.set_size_request(-1, TAB_HEIGHT)
        self._fixed.put(self._icons_box, self._revealer_x, self._tab_y)

        # Add background styling to icons box via CSS - same height as grip
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            #dock-icons {
                background: rgba(0, 0, 0, 0.6);
                border: 1px solid #404040;
            }
        """)
        self._icons_box.set_name("dock-icons")
        self._icons_box.set_size_request(-1, TAB_HEIGHT)
        self._icons_box.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._left_grip_event_box = Gtk.EventBox()
        self._left_grip_event_box.set_above_child(False)
        self._left_grip_event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
        )

        self._left_grip_draw = Gtk.DrawingArea()
        self._left_grip_draw.set_size_request(TAB_WIDTH, TAB_HEIGHT)
        self._left_grip_draw.connect("draw", self._on_draw_left_grip)
        self._left_grip_event_box.add(self._left_grip_draw)
        self._fixed.put(self._left_grip_event_box, 0, self._tab_y)
        self._left_grip_event_box.hide()

        self._icons_box.hide()

        self._tab_event_box = Gtk.EventBox()
        self._tab_event_box.set_above_child(False)
        self._tab_event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        self._tab_draw = Gtk.DrawingArea()
        self._tab_draw.set_size_request(TAB_WIDTH, TAB_HEIGHT)
        self._tab_draw.connect("draw", self._on_draw_grip)
        self._tab_event_box.add(self._tab_draw)
        self._fixed.put(self._tab_event_box, 0, self._tab_y)

    def _setup_events(self):
        self._window.connect("button-press-event", self._on_window_button_press)

        self._tab_event_box.connect("button-press-event", self._on_tab_press)
        self._tab_event_box.connect("button-release-event", self._on_tab_release)
        self._tab_event_box.connect("motion-notify-event", self._on_tab_motion)
        self._tab_event_box.connect("enter-notify-event", self._on_tab_enter)
        self._tab_event_box.connect("leave-notify-event", self._on_tab_leave)

        self._left_grip_event_box.connect(
            "button-press-event", self._on_left_grip_press
        )
        self._left_grip_event_box.connect(
            "button-release-event", self._on_left_grip_release
        )

    def get_icons_box(self):
        return self._icons_box

    def toggle_expand(self):
        new_state = not self._expanded
        self._set_expanded_state(new_state)
        self._app.save_state()

    def _set_expanded_state(self, expanded: bool):
        self._expanded = expanded
        if expanded:
            self._icons_box.show_all()
            for child in self._icons_box.get_children():
                child.show_all()
                child.set_visible(True)
                child.queue_draw()
            self._left_grip_event_box.show()
            log.info(
                f"Dock {self._index}: Expanded, icons_box visible={self._icons_box.get_visible()}, children={len(self._icons_box.get_children())}"
            )
        else:
            self._icons_box.hide()
            self._left_grip_event_box.hide()
        self._update_grip_position()

    def set_expanded(self, expanded: bool):
        self._set_expanded_state(expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def _on_draw_grip(self, widget, cr):
        self._renderer.draw_grip_tab(cr, 0, 0, TAB_WIDTH, TAB_HEIGHT, self._expanded)
        return False

    def _on_draw_background(self, widget, cr):
        alloc = widget.get_allocation()
        self._renderer.draw_background(cr, alloc.width, alloc.height)
        return False

    def _on_draw_left_grip(self, widget, cr):
        self._renderer.draw_left_grip(cr, 0, 0, TAB_WIDTH, TAB_HEIGHT)
        return False

    def _on_tab_press(self, widget, event):
        if event.button == 1:
            self._button_pressed = True
            self._drag_start_y = event.y_root
            self._drag_start_margin = self._app.get_margin_top()
            self._is_dragging = False
            win = widget.get_window()
            if win:
                cursor = Gdk.Cursor.new_from_name(widget.get_display(), "grabbing")
                win.set_cursor(cursor)
        return True

    def _on_tab_release(self, widget, event):
        log.info(f"Dock {self._index}: RIGHT grip release")
        if event.button != 1:
            return True

        self._button_pressed = False
        win = widget.get_window()
        if win:
            win.set_cursor(None)

        if self._is_dragging:
            self._is_dragging = False
            self._app.save_state()
        else:
            self.toggle_expand()
        return True

    def _on_tab_motion(self, widget, event):
        if not self._button_pressed:
            return True

        delta = event.y_root - self._drag_start_y

        if not self._is_dragging and abs(delta) < 20:
            return True

        self._is_dragging = True

        dock_height = self._app.get_window_height()
        screen_height = self._app.get_screen_height()
        max_margin = max(0, screen_height - dock_height - 20)
        new_margin = int(self._drag_start_margin + delta)
        new_margin = max(0, min(new_margin, max_margin))

        self._app.set_margin_top(new_margin)
        return True

    def _on_tab_enter(self, widget, event):
        win = widget.get_window()
        if win:
            cursor = Gdk.Cursor.new_from_name(widget.get_display(), "grab")
            win.set_cursor(cursor)
        return False

    def _on_tab_leave(self, widget, event):
        if not self._button_pressed:
            win = widget.get_window()
            if win:
                win.set_cursor(None)
        return False

    def _on_left_grip_press(self, widget, event):
        log.info(
            f"Dock {self._index}: LEFT grip press, visible={widget.get_visible()}, sensitive={widget.get_sensitive()}"
        )
        if event.button == 1:
            self._button_pressed = True
            self._drag_start_y = event.y_root
            self._drag_start_margin = self._app.get_margin_top()
            self._is_dragging = False
            win = widget.get_window()
            if win:
                cursor = Gdk.Cursor.new_from_name(widget.get_display(), "grabbing")
                win.set_cursor(cursor)
        return True

    def _on_left_grip_release(self, widget, event):
        log.info(f"Dock {self._index}: LEFT grip release")
        if event.button != 1:
            return True

        self._button_pressed = False
        win = widget.get_window()
        if win:
            win.set_cursor(None)

        if self._is_dragging:
            self._is_dragging = False
            self._app.save_state()
        else:
            log.info(f"Dock {self._index}: calling toggle_expand from left grip")
            self.toggle_expand()
        return True

    def _update_grip_position(self):
        if self._expanded:
            width = self._icons_box.get_allocated_width() or TAB_WIDTH
            self._fixed.move(self._tab_event_box, self._revealer_x + width, self._tab_y)
            self._fixed.move(self._left_grip_event_box, 0, self._tab_y)
        else:
            self._fixed.move(self._tab_event_box, 0, self._tab_y)

    def _on_window_button_press(self, widget, event):
        self._app.dismiss_popovers()
        return False

    def _load_icons(self):
        """Load desktop entries and create DockIcon instances."""
        try:
            entries = scan_desktop_entries()
            grouped = group_entries(entries)
        except Exception as e:
            log.error(f"Error scanning desktop entries: {e}")
            return

        log.info(f"Dock {self._index}: Creating icons, grouped items: {len(grouped)}")
        for item in grouped:
            if hasattr(item, "entries"):
                # This is a group, skip for now
                pass
            else:
                icon = DockIcon(item, self._icons_box, self._tracker, self)
                self._dock_icons.append(icon)
        log.info(f"Dock {self._index}: Created {len(self._dock_icons)} icons")
        self._refresh_running_indicators()

    def _refresh_running_indicators(self):
        """Update running indicators for all icons."""
        for icon in self._dock_icons:
            is_running = self._tracker.is_running(
                icon._entry.exec_cmd, icon._entry.filename
            )
            icon.set_running(is_running)
