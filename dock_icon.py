"""Individual dock icon with proper event handling - fixed size."""

import shlex
import subprocess
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from config import TAB_HEIGHT, ICON_SIZE, GDKSUDO_CMD, TERMINAL_CMD
from logger import log

ICON_SIZE_FIXED = 32
ICON_DRAG_THRESHOLD = 10
ICON_EVENT_BOX_BASE_Y = -2
ICON_CONTAINER_WIDTH = 52


class DockIcon:
    """Individual icon with its own event handlers."""

    def __init__(self, slot, icons_box, tracker=None, dock_instance=None):
        self._slot = slot
        self._is_group = slot.get("type") == "group"
        self._app = slot.get("representative") if self._is_group else slot.get("app")
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
        self._pressed = False
        self._dragged = False
        self._press_x_root = 0
        self._press_y_root = 0
        self._context_menu = None
        self._menu_open = False
        self._build_icon()

    def _build_icon(self):
        """Create the icon widget with fixed size."""
        # Fixed size container - 52px width matching grip height
        self._container = Gtk.Fixed()
        self._container.set_size_request(ICON_CONTAINER_WIDTH, TAB_HEIGHT)

        # EventBox to catch events (instead of Button)
        self._event_box = Gtk.EventBox()
        tooltip = self._app.get("name", "")
        if self._is_group:
            tooltip = f"Grupo: {tooltip}"
        self._event_box.set_tooltip_text(tooltip)
        self._event_box.set_size_request(ICON_CONTAINER_WIDTH, TAB_HEIGHT)
        self._event_box.set_above_child(False)
        self._event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
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
        self._event_box.connect("motion-notify-event", self._on_motion)
        self._event_box.connect("button-release-event", self._on_button_release)
        self._event_box.connect("enter-notify-event", self._on_enter)
        self._event_box.connect("leave-notify-event", self._on_leave)

        # Indicator - 1px larger (8px height)
        self._indicator = Gtk.DrawingArea()
        self._indicator.set_size_request(ICON_SIZE_FIXED, 8)
        self._indicator.connect("draw", self._on_draw_indicator)

        # Put in Fixed container - raise indicator by 2px
        self._container.put(self._event_box, 0, ICON_EVENT_BOX_BASE_Y)
        indicator_x = (ICON_CONTAINER_WIDTH - ICON_SIZE_FIXED) // 2
        self._container.put(self._indicator, indicator_x, TAB_HEIGHT - 8)
        self._container.show_all()

        # Add to icons box - no expand
        self._icons_box.pack_start(self._container, False, False, 0)

    def _load_icon(self):
        """Load icon at max size (64px) for zoom capability."""
        if self._is_group:
            if self._load_group_icon():
                return

        icon_name = self._app.get("icon_name")
        if icon_name:
            try:
                theme = Gtk.IconTheme.get_default()
                self._pixbuf = theme.load_icon(icon_name, 64, 0)
                if self._pixbuf:
                    scaled = self._pixbuf.scale_simple(
                        ICON_SIZE_FIXED, ICON_SIZE_FIXED, GdkPixbuf.InterpType.HYPER
                    )
                    if scaled:
                        self._image.set_from_pixbuf(scaled)
                        return
            except Exception:
                pass

        try:
            theme = Gtk.IconTheme.get_default()
            self._pixbuf = theme.load_icon("application-x-executable", 64, 0)
            if self._pixbuf:
                scaled = self._pixbuf.scale_simple(
                    ICON_SIZE_FIXED, ICON_SIZE_FIXED, GdkPixbuf.InterpType.HYPER
                )
                if scaled:
                    self._image.set_from_pixbuf(scaled)
                    return
        except Exception:
            pass
        self._image.set_from_icon_name("application-x-executable", Gtk.IconSize.BUTTON)

    def _load_group_icon(self) -> bool:
        """Render a folder icon with mini overlay for grouped apps."""
        try:
            theme = Gtk.IconTheme.get_default()
            base = theme.load_icon("folder", 64, 0)
            mini_name = self._app.get("icon_name") or "application-x-executable"
            mini = theme.load_icon(mini_name, 24, 0)
            if not base or not mini:
                return False

            composed = base.copy()
            mini.composite(
                composed,
                36,
                4,
                24,
                24,
                36,
                4,
                1.0,
                1.0,
                GdkPixbuf.InterpType.BILINEAR,
                255,
            )
            self._pixbuf = composed
            scaled = self._pixbuf.scale_simple(
                ICON_SIZE_FIXED, ICON_SIZE_FIXED, GdkPixbuf.InterpType.HYPER
            )
            if scaled:
                self._image.set_from_pixbuf(scaled)
                return True
        except Exception:
            return False
        return False

    def _launch_app(self, with_sudo=False, in_terminal=False):
        """Launch the application with optional modifiers."""
        exec_cmd = self._app.get("exec_cmd")
        if not exec_cmd:
            return

        try:
            args = shlex.split(exec_cmd)
            if with_sudo or self._app.get("launch_sudo"):
                args = [GDKSUDO_CMD, "--message", f"Launching {self._app.get('name')}", "--"] + args
            elif in_terminal or self._app.get("terminal"):
                terminal_cmd = TERMINAL_CMD.split()
                args = terminal_cmd + args
            home = os.path.expanduser("~")
            subprocess.Popen(
                args,
                start_new_session=True,
                cwd=home,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.error(f"Failed to launch '{exec_cmd}': {e}")

    def _show_context_menu(self, event):
        menu = Gtk.Menu()
        self._context_menu = menu
        self._menu_open = True
        menu.connect("deactivate", self._on_menu_deactivate)

        if self._is_group:
            self._show_group_menu(menu)
            menu.show_all()
            menu.popup_at_pointer(event)
            return

        launch_normal = Gtk.MenuItem(label="Iniciar")
        launch_normal.connect("activate", lambda _: self._launch_app())
        menu.append(launch_normal)

        if self._app.get("terminal") or self._app.get("launch_sudo"):
            submenu = Gtk.Menu()

            launch_sub = Gtk.MenuItem(label="Iniciar como")
            submenu.append(launch_sub)

            if self._app.get("launch_sudo"):
                sudo_item = Gtk.MenuItem(label="Con sudo")
                sudo_item.connect("activate", lambda _: self._launch_app(with_sudo=True))
                submenu.append(sudo_item)

            if self._app.get("terminal"):
                term_item = Gtk.MenuItem(label="En terminal")
                term_item.connect("activate", lambda _: self._launch_app(in_terminal=True))
                submenu.append(term_item)

            launch_sub.set_submenu(submenu)

        menu.append(Gtk.SeparatorMenuItem())

        hide_item = Gtk.MenuItem(label="Ocultar del dock")
        hide_item.connect("activate", self._on_hide_app)
        menu.append(hide_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_menu_deactivate(self, _menu):
        self._menu_open = False
        self._context_menu = None

    def _show_group_menu(self, menu: Gtk.Menu):
        for grouped_app in self._slot.get("apps", []):
            item = Gtk.MenuItem(label=grouped_app.get("name", "App"))
            item.connect("activate", lambda _, app=grouped_app: self._launch_specific_app(app))
            menu.append(item)

    def _launch_specific_app(self, app: dict):
        exec_cmd = app.get("exec_cmd")
        if not exec_cmd:
            return
        try:
            args = shlex.split(exec_cmd)
            if app.get("launch_sudo"):
                args = [GDKSUDO_CMD, "--message", f"Launching {app.get('name')}", "--"] + args
            elif app.get("terminal"):
                args = TERMINAL_CMD.split() + args
            subprocess.Popen(
                args,
                start_new_session=True,
                cwd=os.path.expanduser("~"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.error(f"Failed to launch '{exec_cmd}': {e}")

    def _on_hide_app(self, _):
        db = self._dock_instance._app.get_database()
        db.update_app(self._app["id"], enabled=0)
        self._dock_instance.refresh_icons()

    def _on_button_press(self, widget, event):
        if self._menu_open:
            return True
        if event.button == 1:
            self._pressed = True
            self._dragged = False
            self._press_x_root = event.x_root
            self._press_y_root = event.y_root
            self._cancel_zoom_anim()
            return False
        elif event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _on_motion(self, widget, event):
        if not self._pressed:
            return False
        dx = abs(event.x_root - self._press_x_root)
        dy = abs(event.y_root - self._press_y_root)
        if dx >= ICON_DRAG_THRESHOLD or dy >= ICON_DRAG_THRESHOLD:
            self._dragged = True
        return False

    def _on_button_release(self, widget, event):
        if event.button != 1:
            return False
        was_pressed = self._pressed
        was_dragged = self._dragged
        self._pressed = False
        self._dragged = False

        if not was_pressed:
            return False

        if was_dragged:
            return False

        log.info(f"DockIcon RELEASE LAUNCH: {self._app.get('name')}")
        if self._is_group:
            self._show_context_menu(event)
        else:
            self._launch_app()
            self._start_bounce_anim()
        return False

    def _on_enter(self, widget, event):
        log.info(f"DockIcon ENTER: {self._app.get('name')}")
        self._start_zoom_in_anim()

    def _on_leave(self, widget, event):
        log.info(f"DockIcon LEAVE: {self._app.get('name')}")
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
        if self._bounce_timeout_id:
            GLib.source_remove(self._bounce_timeout_id)
            self._bounce_timeout_id = None

        offset = 0
        direction = -1
        collapse_scheduled = False

        def bounce_step():
            nonlocal offset, direction, collapse_scheduled
            # Check if dock is still expanded
            if self._dock_instance and not self._dock_instance.is_expanded():
                self._container.move(self._event_box, 0, ICON_EVENT_BOX_BASE_Y)
                self._bounce_timeout_id = None
                return False

            offset += direction
            if offset <= -12:
                direction = 1
            elif offset >= 0:
                self._container.move(self._event_box, 0, ICON_EVENT_BOX_BASE_Y)
                # Schedule collapse after 2 seconds if not already scheduled
                if not collapse_scheduled and self._dock_instance:
                    collapse_scheduled = True
                    GLib.timeout_add_seconds(2, self._collapse_dock)
                # Keep bouncing - reset offset and direction
                offset = 0
                direction = -1
                return True
            self._container.move(self._event_box, 0, ICON_EVENT_BOX_BASE_Y + offset)
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

    def mark_dragged(self):
        self._dragged = True

    def reset_dragged(self):
        self._dragged = False

    def has_open_menu(self) -> bool:
        return self._menu_open

    def close_menu(self):
        if self._context_menu:
            self._context_menu.popdown()

    def get_slot(self) -> dict:
        return self._slot

    def get_app_ids(self) -> list[int]:
        if self._is_group:
            return [app["id"] for app in self._slot.get("apps", [])]
        return [self._app["id"]]
