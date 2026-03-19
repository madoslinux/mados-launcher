"""Individual dock icon with proper event handling - fixed size."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from mados_launcher.config import TAB_HEIGHT, ICON_SIZE
from mados_launcher.desktop_entries import launch_application
from mados_launcher.logger import log

ICON_SIZE_FIXED = 32


class DockIcon:
    """Individual icon with its own event handlers."""

    def __init__(self, entry, icons_box, tracker=None, dock_instance=None):
        self._entry = entry
        self._icons_box = icons_box
        self._tracker = tracker
        self._dock_instance = dock_instance
        self._running = False
        self._bounce_timeout_id = None
        self._zoom_animating = False
        self._current_zoom_size = ICON_SIZE_FIXED
        self._zoom_timeout_id = None
        self._image = None
        self._pixbuf = None
        self._build_icon()

    def _build_icon(self):
        """Create the icon widget with fixed size."""
        # Fixed size container - 52px width matching grip height
        self._container = Gtk.Fixed()
        self._container.set_size_request(52, TAB_HEIGHT)

        # EventBox to catch events (instead of Button)
        self._event_box = Gtk.EventBox()
        self._event_box.set_tooltip_text(self._entry.name)
        self._event_box.set_size_request(52, TAB_HEIGHT)
        self._event_box.set_above_child(False)
        self._event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        # Image inside event box
        self._image = Gtk.Image()
        self._image.set_halign(Gtk.Align.CENTER)
        self._image.set_valign(Gtk.Align.CENTER)
        self._load_icon()
        self._event_box.add(self._image)
        self._event_box.show_all()

        # Connect signals
        self._event_box.connect("button-press-event", self._on_button_press)
        self._event_box.connect("enter-notify-event", self._on_enter)
        self._event_box.connect("leave-notify-event", self._on_leave)

        # Indicator - 1px larger (8px height)
        self._indicator = Gtk.DrawingArea()
        self._indicator.set_size_request(ICON_SIZE_FIXED, 8)
        self._indicator.connect("draw", self._on_draw_indicator)

        # Put in Fixed container - raise indicator by 2px
        self._container.put(self._event_box, 0, -2)  # move up 2px
        self._container.put(self._indicator, 0, TAB_HEIGHT - 8)
        self._container.show_all()

        # Add to icons box - no expand
        self._icons_box.pack_start(self._container, False, False, 0)

    def _load_icon(self):
        """Load icon at max size (64px) for zoom capability."""
        if self._entry.icon_name:
            try:
                theme = Gtk.IconTheme.get_default()
                self._pixbuf = theme.load_icon(self._entry.icon_name, 64, 0)
                if self._pixbuf:
                    scaled = self._pixbuf.scale_simple(
                        ICON_SIZE_FIXED, ICON_SIZE_FIXED, GdkPixbuf.InterpType.HYPER
                    )
                    if scaled:
                        self._image.set_from_pixbuf(scaled)
                        return
            except Exception:
                pass

        self._image.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)

    def _on_button_press(self, widget, event):
        if event.button == 1:
            log.info(f"DockIcon CLICKED: {self._entry.name}")
            self._cancel_zoom_anim()
            launch_application(self._entry.exec_cmd, self._entry.terminal)
            self._start_bounce_anim()
        return True

    def _on_enter(self, widget, event):
        log.info(f"DockIcon ENTER: {self._entry.name}")
        self._start_zoom_in_anim()

    def _on_leave(self, widget, event):
        log.info(f"DockIcon LEAVE: {self._entry.name}")
        self._start_zoom_out_anim()

    def _on_draw_indicator(self, widget, cr):
        if not self._running:
            return
        alloc = widget.get_allocation()
        cr.set_source_rgb(0.2, 0.8, 0.2)
        cr.arc(alloc.width / 2, alloc.height / 2, 2, 0, 2 * 3.14159)
        cr.fill()

    def _start_zoom_in_anim(self):
        if self._zoom_timeout_id:
            GLib.source_remove(self._zoom_timeout_id)
        self._zoom_animating = True
        self._current_zoom_size = ICON_SIZE_FIXED
        self._animate_zoom(48, True)

    def _start_zoom_out_anim(self):
        if self._zoom_timeout_id:
            GLib.source_remove(self._zoom_timeout_id)
        self._zoom_animating = True
        self._current_zoom_size = 48
        self._animate_zoom(ICON_SIZE_FIXED, False)

    def _animate_zoom(self, target_size, zoom_in):
        step_size = 2 if zoom_in else -2

        def step():
            nonlocal step_size
            if not self._zoom_animating:
                return False

            new_size = self._current_zoom_size + step_size

            if zoom_in and new_size >= target_size:
                new_size = target_size
                self._zoom_animating = False
                self._zoom_timeout_id = None
            elif not zoom_in and new_size <= target_size:
                new_size = target_size
                self._zoom_animating = False
                self._zoom_timeout_id = None

            self._current_zoom_size = new_size

            if self._pixbuf:
                scaled = self._pixbuf.scale_simple(
                    int(self._current_zoom_size),
                    int(self._current_zoom_size),
                    GdkPixbuf.InterpType.HYPER,
                )
                if scaled:
                    self._image.set_from_pixbuf(scaled)

            return self._zoom_animating

        self._zoom_timeout_id = GLib.timeout_add(16, step)

    def _cancel_zoom_anim(self):
        self._zoom_animating = False
        self._current_zoom_size = ICON_SIZE_FIXED

    def _start_bounce_anim(self):
        offset = 0
        direction = -1
        collapse_scheduled = False

        def bounce_step():
            nonlocal offset, direction, collapse_scheduled
            # Check if dock is still expanded
            if self._dock_instance and not self._dock_instance.is_expanded():
                self._container.move(self._event_box, 0, 0)
                return False

            offset += direction
            if offset <= -12:
                direction = 1
            elif offset >= 0:
                self._container.move(self._event_box, 0, 0)
                # Schedule collapse after 2 seconds if not already scheduled
                if not collapse_scheduled and self._dock_instance:
                    collapse_scheduled = True
                    GLib.timeout_add_seconds(2, self._collapse_dock)
                # Keep bouncing - reset offset and direction
                offset = 0
                direction = -1
                return True
            self._container.move(self._event_box, 0, offset)
            return True

        self._bounce_timeout_id = GLib.timeout_add(24, bounce_step)

    def _collapse_dock(self):
        if self._dock_instance and self._dock_instance.is_expanded():
            self._dock_instance.set_expanded(False)
            self._dock_instance._app.save_state()
        return False

    def set_running(self, running: bool):
        self._running = running
        self._indicator.queue_draw()
