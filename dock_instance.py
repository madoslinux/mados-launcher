"""Single dock instance for one monitor."""

import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk, GdkPixbuf

from config import TAB_WIDTH, TAB_HEIGHT
from dock_renderer import DockRenderer
from dock_icon import DockIcon
from window_tracker import WindowTracker
from logger import log

ICON_SLOT_WIDTH = 52
GROUP_DROP_RADIUS = 12
PUSH_OFFSET = 14
DRAG_START_DELAY_S = 0.15


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
        self._drag_icon = None
        self._drag_icon_start_x = 0
        self._drag_icon_original_index = -1
        self._drag_preview = None
        self._drag_preview_size = 40
        self._drag_press_ts = 0.0
        self._icon_dragging = False
        self._insert_indicator = None
        self._group_target_icon = None
        self._tracker = tracker if tracker else WindowTracker()

        self._build_ui()
        self._setup_events()
        self._load_icons()

    def _build_ui(self):
        self._fixed = Gtk.Fixed()
        self._fixed.set_size_request(TAB_WIDTH, 150)
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

        self._update_window_size()
        self._update_input_shape()

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
            self._icons_box.set_visible(True)
            self._left_grip_event_box.set_visible(True)
        else:
            self._icons_box.set_visible(False)
            self._left_grip_event_box.set_visible(False)
        self._tab_draw.queue_draw()
        self._left_grip_draw.queue_draw()
        self._update_grip_position()
        self._update_window_size()

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
        if event.button == 3:
            self._show_tab_context_menu(event)
            return True
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
        had_open_menu = any(dock_icon.has_open_menu() for dock_icon in self._dock_icons)
        if had_open_menu:
            self._cancel_icon_drag()
        for dock_icon in self._dock_icons:
            if dock_icon.has_open_menu():
                dock_icon.close_menu()
        self._app.dismiss_popovers()
        return False

    def _show_tab_context_menu(self, event):
        menu = Gtk.Menu()

        settings_item = Gtk.MenuItem(label="Configuración...")
        settings_item.connect("activate", lambda _: self._app.open_settings())
        menu.append(settings_item)

        reload_item = Gtk.MenuItem(label="Recargar aplicaciones")
        reload_item.connect("activate", lambda _: self.refresh_icons())
        menu.append(reload_item)

        menu.append(Gtk.SeparatorMenuItem())

        close_item = Gtk.MenuItem(label="Cerrar dock")
        close_item.connect("activate", lambda _: Gtk.main_quit())
        menu.append(close_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _load_icons(self):
        """Load desktop entries from database and create DockIcon instances."""
        try:
            db = self._app.get_database()
            slots = db.resolve_dock_slots(enabled_only=True)
        except Exception as e:
            log.error(f"Error loading apps from database: {e}")
            return

        for child in self._icons_box.get_children():
            self._icons_box.remove(child)
        self._dock_icons = []

        for slot in slots:
            icon = DockIcon(slot, self._icons_box, self._tracker, self)
            self._dock_icons.append(icon)
            icon._event_box.connect("button-press-event", self._on_icon_press, icon)
            icon._event_box.connect("motion-notify-event", self._on_icon_motion, icon)
            icon._event_box.connect("button-release-event", self._on_icon_release, icon)

        log.info(f"Dock {self._index}: Created {len(self._dock_icons)} icons")
        self._refresh_running_indicators()
        self._update_window_size()

    def refresh_icons(self):
        """Reload icons from database."""
        self._load_icons()

    def _on_icon_press(self, widget, event, icon):
        if event.button != 1 or not self._expanded:
            return False
        if icon.has_open_menu():
            self._cancel_icon_drag()
            return True

        for dock_icon in self._dock_icons:
            if dock_icon is not icon and dock_icon.has_open_menu():
                dock_icon.close_menu()

        self._drag_icon = icon
        self._drag_icon_start_x = event.x_root
        self._drag_icon_original_index = self._dock_icons.index(icon)
        self._drag_press_ts = time.monotonic()
        self._icon_dragging = False
        icon.reset_dragged()
        icon._container.set_opacity(0.7)
        return False

    def _on_icon_motion(self, widget, event, icon):
        if not self._drag_icon or icon is not self._drag_icon:
            return False

        if self._drag_icon_original_index < 0:
            return False

        delta = event.x_root - self._drag_icon_start_x
        if abs(delta) < 8:
            if self._drag_preview:
                self._move_drag_preview(event.x_root, event.y_root)
            return False

        if not self._icon_dragging:
            if (time.monotonic() - self._drag_press_ts) < DRAG_START_DELAY_S:
                return False
            self._icon_dragging = True
            self._create_drag_preview(icon, event.x_root, event.y_root)

        icon.mark_dragged()

        current_index = self._dock_icons.index(self._drag_icon)
        target_index, center_dist = self._pointer_target_index(event.x_root)
        if target_index is None:
            return False

        target_icon = self._dock_icons[target_index] if 0 <= target_index < len(self._dock_icons) else None
        if (
            target_icon
            and target_icon is not self._drag_icon
            and center_dist <= GROUP_DROP_RADIUS
        ):
            self._set_group_target(target_icon)
            self._hide_insert_indicator()
            self._reset_push_preview()
        else:
            self._set_group_target(None)
            insert_index = self._pointer_insert_index(event.x_root)
            self._show_insert_indicator(insert_index)
            self._apply_push_preview(insert_index)

        self._move_drag_preview(event.x_root, event.y_root)
        return False

    def _on_icon_release(self, widget, event, icon):
        if event.button != 1 or not self._drag_icon:
            return False

        self._drag_icon._container.set_opacity(1.0)
        self._destroy_drag_preview()
        self._hide_insert_indicator()
        self._reset_push_preview()
        self._set_group_target(None)

        target_index, center_dist = self._pointer_target_index(event.x_root)
        if (
            target_index is not None
            and 0 <= target_index < len(self._dock_icons)
            and center_dist <= GROUP_DROP_RADIUS
        ):
            target_icon = self._dock_icons[target_index]
            if target_icon is not self._drag_icon:
                self._app.get_database().assign_manual_group(
                    self._drag_icon.get_app_ids(), target_icon.get_app_ids()
                )
                self.refresh_icons()
                self._drag_icon = None
                self._drag_icon_original_index = -1
                return False

        if not self._icon_dragging:
            self._drag_icon = None
            self._drag_icon_original_index = -1
            self._icon_dragging = False
            return False

        insert_index = self._pointer_insert_index(event.x_root)
        if self._reorder_dragged_icon(insert_index):
            self._persist_icon_order()

        self._drag_icon = None
        self._drag_icon_original_index = -1
        self._icon_dragging = False
        return False

    def _cancel_icon_drag(self):
        if self._drag_icon:
            self._drag_icon._container.set_opacity(1.0)
        self._destroy_drag_preview()
        self._hide_insert_indicator()
        self._reset_push_preview()
        self._set_group_target(None)
        self._drag_icon = None
        self._drag_icon_original_index = -1
        self._icon_dragging = False

    def _reorder_dragged_icon(self, insert_index: int) -> bool:
        if not self._drag_icon:
            return False
        current_index = self._dock_icons.index(self._drag_icon)
        target_index = max(0, min(insert_index, len(self._dock_icons)))
        if target_index > current_index:
            target_index -= 1
        if target_index == current_index:
            return False

        self._dock_icons.insert(target_index, self._dock_icons.pop(current_index))
        for child in self._icons_box.get_children():
            self._icons_box.remove(child)
        for dock_icon in self._dock_icons:
            self._icons_box.pack_start(dock_icon._container, False, False, 0)
        self._icons_box.show_all()
        return True

    def _create_drag_preview(self, icon, x_root, y_root):
        self._destroy_drag_preview()

        preview = Gtk.Image()
        if icon._pixbuf:
            scaled = icon._pixbuf.scale_simple(
                self._drag_preview_size,
                self._drag_preview_size,
                GdkPixbuf.InterpType.BILINEAR,
            )
            if scaled:
                preview.set_from_pixbuf(scaled)
            else:
                preview.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        else:
            preview.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)

        self._drag_preview = preview
        self._fixed.put(self._drag_preview, 0, 0)
        self._drag_preview.show()
        self._move_drag_preview(x_root, y_root)

    def _move_drag_preview(self, x_root, y_root):
        if not self._drag_preview:
            return
        gdk_win = self._window.get_window()
        if not gdk_win:
            return
        origin = gdk_win.get_origin()
        if isinstance(origin, tuple) and len(origin) == 2:
            origin_x, origin_y = origin
        elif isinstance(origin, tuple) and len(origin) == 3:
            _, origin_x, origin_y = origin
        else:
            return

        local_x = int(x_root - origin_x - (self._drag_preview_size // 2))
        local_y = int(y_root - origin_y - (self._drag_preview_size // 2))
        self._fixed.move(self._drag_preview, local_x, local_y)

    def _destroy_drag_preview(self):
        if not self._drag_preview:
            return
        self._fixed.remove(self._drag_preview)
        self._drag_preview = None

    def _ensure_insert_indicator(self):
        if self._insert_indicator:
            return
        self._insert_indicator = Gtk.EventBox()
        self._insert_indicator.set_visible_window(True)
        self._insert_indicator.set_size_request(3, TAB_HEIGHT - 4)
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"#drop-indicator { background: rgba(136, 192, 208, 0.95); border-radius: 2px; }"
        )
        self._insert_indicator.set_name("drop-indicator")
        self._insert_indicator.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._fixed.put(self._insert_indicator, self._revealer_x, self._tab_y + 2)

    def _show_insert_indicator(self, insert_index: int):
        if insert_index is None:
            return
        self._ensure_insert_indicator()
        if not self._insert_indicator:
            return
        x = self._revealer_x + (insert_index * ICON_SLOT_WIDTH) - 1
        self._fixed.move(self._insert_indicator, x, self._tab_y + 2)
        self._insert_indicator.show()

    def _hide_insert_indicator(self):
        if self._insert_indicator:
            self._insert_indicator.hide()

    def _apply_push_preview(self, insert_index: int):
        if not self._drag_icon:
            return
        original_index = self._dock_icons.index(self._drag_icon)
        for idx, dock_icon in enumerate(self._dock_icons):
            if dock_icon is self._drag_icon:
                continue
            offset = 0
            if insert_index > original_index and original_index < idx <= insert_index - 1:
                offset = -PUSH_OFFSET
            elif insert_index < original_index and insert_index <= idx < original_index:
                offset = PUSH_OFFSET
            dock_icon._container.set_margin_start(offset)

    def _reset_push_preview(self):
        for dock_icon in self._dock_icons:
            dock_icon._container.set_margin_start(0)

    def _set_group_target(self, icon):
        if self._group_target_icon and self._group_target_icon is not self._drag_icon:
            self._group_target_icon._container.set_opacity(1.0)
        self._group_target_icon = icon
        if self._group_target_icon and self._group_target_icon is not self._drag_icon:
            self._group_target_icon._container.set_opacity(0.85)

    def _persist_icon_order(self):
        app_ids = []
        for icon in self._dock_icons:
            app_ids.extend(icon.get_app_ids())
        if app_ids:
            self._app.get_database().reorder_apps(app_ids)

    def _pointer_target_index(self, x_root):
        gdk_window = self._icons_box.get_window()
        if not gdk_window:
            return (None, 0)

        origin = gdk_window.get_origin()
        if isinstance(origin, tuple) and len(origin) == 2:
            origin_x = origin[0]
        elif isinstance(origin, tuple) and len(origin) == 3:
            origin_x = origin[1]
        else:
            return (None, 0)

        local_x = max(0, int(x_root - origin_x))
        index = local_x // ICON_SLOT_WIDTH
        if not self._dock_icons:
            return (None, 0)
        index = max(0, min(index, len(self._dock_icons) - 1))

        center_x = index * ICON_SLOT_WIDTH + ICON_SLOT_WIDTH // 2
        return (index, abs(local_x - center_x))

    def _pointer_insert_index(self, x_root):
        gdk_window = self._icons_box.get_window()
        if not gdk_window:
            return 0
        origin = gdk_window.get_origin()
        if isinstance(origin, tuple) and len(origin) == 2:
            origin_x = origin[0]
        elif isinstance(origin, tuple) and len(origin) == 3:
            origin_x = origin[1]
        else:
            return 0

        local_x = max(0, int(x_root - origin_x))
        return max(0, min((local_x + (ICON_SLOT_WIDTH // 2)) // ICON_SLOT_WIDTH, len(self._dock_icons)))

    def _refresh_running_indicators(self):
        """Update running indicators for all icons."""
        for icon in self._dock_icons:
            is_running = self._tracker.is_running(
                icon._app.get("exec_cmd", ""), icon._app.get("filename", "")
            )
            icon.set_running(is_running)

    def _update_input_shape(self):
        """Define el área exacta que captura eventos de mouse."""
        gdk_window = self._window.get_window()
        if not gdk_window:
            return

        if not hasattr(gdk_window, 'input_shape_combine_region'):
            return

        import cairo

        region = cairo.Region()
        region.union(cairo.RectangleInt(0, self._tab_y, TAB_WIDTH, TAB_HEIGHT))

        if self._expanded:
            icons_alloc = self._icons_box.get_allocation()
            if icons_alloc.width > 0:
                region.union(cairo.RectangleInt(
                    self._revealer_x, self._tab_y,
                    icons_alloc.width, icons_alloc.height
                ))

        gdk_window.input_shape_combine_region(region, 0, 0)

    def _update_window_size(self):
        """Ajustar tamaño de ventana al contenido real."""
        if self._expanded:
            n_icons = len(self._dock_icons)
            icon_area_width = n_icons * 52 if n_icons > 0 else 0
            width = TAB_WIDTH + icon_area_width
        else:
            width = TAB_WIDTH

        self._window.resize(width, TAB_HEIGHT)
        self._update_input_shape()
