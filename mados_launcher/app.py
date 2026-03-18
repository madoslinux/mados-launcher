"""Main application class for the madOS Launcher dock."""

import cairo
import json
import math
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

HAS_LAYER_SHELL = False
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    GtkLayerShell = None

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango

from mados_launcher import __app_id__, __app_name__
from mados_launcher.config import (
    NORD,
    ICON_SIZE,
    TAB_WIDTH,
    DOCK_WIDTH,
    TAB_HEIGHT,
    ICON_PADDING,
    ICON_SPACING,
    ANIMATION_DURATION,
    GRIP_DOT_RADIUS,
    GRIP_DOT_SPACING,
    GRIP_DOT_COLS,
    GRIP_DOT_COL_GAP,
    DRAG_THRESHOLD,
    MIN_MARGIN_TOP,
    DEFAULT_MARGIN_TOP,
    CONFIG_DIR,
    STATE_FILE,
    REFRESH_INTERVAL_SECONDS,
    SHADOW_SIZE,
    SHADOW_OFFSET_X,
    SHADOW_OFFSET_Y,
    SHADOW_LAYERS,
    SHADOW_BASE_ALPHA,
    ICON_ZOOM_SIZE,
    ICON_ZOOM_STEP,
    ICON_ZOOM_INTERVAL_MS,
)
from mados_launcher.desktop_entries import scan_desktop_entries, launch_application, group_entries, EntryGroup
from mados_launcher.window_tracker import WindowTracker
from mados_launcher.theme import apply_theme

INDICATOR_HEIGHT = 6
INDICATOR_DOT_RADIUS = 3
WINDOW_POLL_MS = 2000

BOUNCE_AMPLITUDE = 3
BOUNCE_DURATION_MS = 50
BOUNCE_TOTAL_SECONDS = 3


def _hex_to_rgb(hex_color):
    """Convert hex color string to (r, g, b) floats 0-1."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


class LauncherApp:
    """madOS Launcher dock — a retractable icon dock anchored to the left edge."""

    def __init__(self):
        self._expanded = False
        self._is_dragging = False
        self._button_pressed = False
        self._drag_start_y = 0
        self._drag_start_margin = 0
        self._margin_top = DEFAULT_MARGIN_TOP
        self._drag_update_pending = False
        self._pending_margin = 0
        self._screen_height = 768
        self._auto_collapse_id = None
        self._entries = []
        self._grouped = []
        self._icon_buttons = []

        self._zoom_state = {}
        self._bounce_state = {}
        self._active_popover = None

        self._tracker = WindowTracker()
        self._load_state()
        apply_theme()

        self._build_window()
        self._build_ui()
        self._refresh_entries()

        self._expanded = False
        self._revealer.set_reveal_child(False)

        self.window.present()
        self._apply_margin_position()
        self._update_grip_position()

        GLib.timeout_add_seconds(REFRESH_INTERVAL_SECONDS, self._refresh_entries)
        GLib.timeout_add(WINDOW_POLL_MS, self._poll_window_state)

    def _build_window(self):
        """Create the GTK window and configure it as a layer-shell surface."""
        self.window = Gtk.Window()
        self.window.set_title(__app_name__)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_name("mados-launcher-window")
        self.window.set_size_request(-1, 52)

        if HAS_LAYER_SHELL:
            GtkLayerShell.init_for_window(self.window)
            GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_namespace(self.window, __app_id__)

            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, False)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, False)

            GtkLayerShell.set_exclusive_zone(self.window, 0)
            GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, self._margin_top)
            GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.LEFT, 0)
            GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        else:
            self.window.set_visible(True)
            self.window.set_focusable(False)
            # Apply margin position
            self._apply_margin_position()

        display = Gdk.Display.get_default()
        if display:
            try:
                monitor = display.get_monitor(0)
                if monitor:
                    geom = monitor.get_geometry()
                    self._screen_height = geom.height
            except Exception:
                pass

        self.window.connect("destroy", self._on_destroy)

        controller = Gtk.GestureClick()
        controller.connect("pressed", self._on_window_button_press)
        self.window.add_controller(controller)

    def _build_ui(self):
        """Build the dock UI: [revealer with icons] [grip tab]."""
        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self._revealer.set_transition_duration(ANIMATION_DURATION)
        self._revealer.connect("notify::child-revealed", self._on_revealer_animation_done)

        self._fixed = Gtk.Fixed()
        self._fixed.set_size_request(-1, 52)
        self.window.set_child(self._fixed)

        # Los iconos y grips en la misma posición Y (parte superior)
        self._revealer_x = TAB_WIDTH

        self._visual_bg = Gtk.DrawingArea()
        self._visual_bg.set_size_request(100, 52)
        self._visual_bg.set_draw_func(self._on_draw_visual_bg)
        self._fixed.put(self._visual_bg, 0, 0)

        self._icons_bg = None

        self._icons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._icons_box.set_size_request(-1, 52)
        self._icons_box.set_margin_top(5)
        self._revealer.set_child(self._icons_box)

        self._fixed.put(self._revealer, self._revealer_x, 0)

        self._tab_y = 0  # Misma línea que los iconos

        self._tab_draw = Gtk.DrawingArea()
        self._tab_draw.set_name("grip-tab")
        self._tab_draw.set_size_request(TAB_WIDTH, TAB_HEIGHT)
        self._tab_draw.set_draw_func(self._on_draw_grip)
        self._fixed.put(self._tab_draw, 0, self._tab_y)

        self._left_grip_draw = Gtk.DrawingArea()
        self._left_grip_draw.set_name("left-grip")
        self._left_grip_draw.set_size_request(TAB_WIDTH, TAB_HEIGHT)
        self._left_grip_draw.set_draw_func(self._on_draw_left_grip)
        self._left_grip_draw.set_visible(False)
        self._fixed.put(self._left_grip_draw, 0, self._tab_y)

        self._left_grip_controller = Gtk.GestureClick()
        self._left_grip_controller.set_button(0)
        self._left_grip_controller.connect("pressed", self._on_left_grip_press)
        self._left_grip_controller.connect("released", self._on_left_grip_release)
        self._left_grip_draw.add_controller(self._left_grip_controller)

        self._tab_controller = Gtk.GestureClick()
        self._tab_controller.set_button(0)
        self._tab_controller.connect("pressed", self._on_tab_press)
        self._tab_controller.connect("released", self._on_tab_release)
        self._tab_draw.add_controller(self._tab_controller)

        self._motion_controller = Gtk.EventControllerMotion()
        self._motion_controller.connect("motion", self._on_tab_motion)
        self._motion_controller.connect("enter", self._on_tab_enter)
        self._motion_controller.connect("leave", self._on_tab_leave)
        self._tab_draw.add_controller(self._motion_controller)
        self._motion_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

    def _on_window_draw(self, widget, cr, data):
        """Clear background to 100% transparent."""
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False

    def _on_draw_grip(self, area, cr, width, height, data=None):
        """Draw the grip handle."""
        w, h = width, height

        radius = 8
        cr.new_path()
        cr.move_to(0, 0)
        cr.line_to(w - radius, 0)
        cr.arc(w - radius, radius, radius, -math.pi / 2, 0)
        cr.line_to(w, h - radius)
        cr.arc(w - radius, h - radius, radius, 0, math.pi / 2)
        cr.line_to(0, h)
        cr.close_path()

        bg = _hex_to_rgb(NORD["nord1"])
        cr.set_source_rgb(*bg)
        cr.fill()

        dot_color = _hex_to_rgb(NORD["nord3"])
        cr.set_source_rgb(*dot_color)

        total_dot_rows = 5
        total_height = (total_dot_rows - 1) * GRIP_DOT_SPACING
        start_y = (h - total_height) / 2
        center_x = w / 2

        for row in range(total_dot_rows):
            y = start_y + row * GRIP_DOT_SPACING
            for col in range(GRIP_DOT_COLS):
                offset = (col - (GRIP_DOT_COLS - 1) / 2) * GRIP_DOT_COL_GAP
                x = center_x + offset
                cr.arc(x, y, GRIP_DOT_RADIUS, 0, 2 * math.pi)
                cr.fill()

        chevron_color = _hex_to_rgb(NORD["nord9"])
        cr.set_source_rgba(*chevron_color, 0.6)
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        chevron_y = h - 14
        cx = w / 2

        if self._expanded:
            cr.move_to(cx + 3, chevron_y - 4)
            cr.line_to(cx - 2, chevron_y)
            cr.line_to(cx + 3, chevron_y + 4)
        else:
            cr.move_to(cx - 3, chevron_y - 4)
            cr.line_to(cx + 2, chevron_y)
            cr.line_to(cx - 3, chevron_y + 4)

        cr.stroke()
        return False

    def _on_tab_press(self, controller, n_press, x, y):
        """Record starting position for potential drag."""
        self._button_pressed = True
        self._drag_start_y = y
        self._drag_start_margin = self._margin_top
        self._is_dragging = False
        self._tab_draw.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
        return True

    def _on_tab_release(self, controller, n_press, x, y):
        """On release: toggle if click, save if drag."""
        self._button_pressed = False

        if self._is_dragging:
            self._is_dragging = False
            self._save_state()
        else:
            self._expanded = not self._expanded
            self._revealer.set_reveal_child(self._expanded)
            self._update_grip_position()
            self._tab_draw.queue_draw()
            self._save_state()

        self._tab_draw.set_cursor(Gdk.Cursor.new_from_name("grab"))
        return True

    def _on_tab_motion(self, controller, x, y):
        """Handle vertical drag while button is held."""
        if not self._button_pressed:
            return True

        delta = y - self._drag_start_y

        if not self._is_dragging and abs(delta) < DRAG_THRESHOLD:
            return True

        self._is_dragging = True

        dock_height = self.window.get_height()
        max_margin = max(0, self._screen_height - dock_height - 20)
        new_margin = int(self._drag_start_margin + delta)
        new_margin = max(MIN_MARGIN_TOP, min(new_margin, max_margin))

        self._pending_margin = new_margin
        if not self._drag_update_pending:
            self._drag_update_pending = True
            GLib.idle_add(self._flush_drag_position)

        return True

    def _apply_margin_position(self):
        """Apply the current margin_top position to the window."""
        if HAS_LAYER_SHELL:
            GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, self._margin_top)
        else:
            # Set size first
            self.window.set_default_size(200, 52)
            # Try using surface position after window is shown
            GLib.timeout_add(100, self._position_window)
            
    def _position_window(self):
        """Position the window at left edge."""
        try:
            surface = self.window.get_surface()
            # Get monitor work area
            display = Gdk.Display.get_default()
            monitor = display.get_monitor(0)
            work = monitor.get_workarea()
            
            # Position at left edge (x=0), below taskbar (y = work.y + margin)
            x = work.x  # Usually 0
            y = work.y + self._margin_top
            
            surface.set_position(x, y)
        except Exception as e:
            # Fallback: just set at 0, margin_top
            try:
                surface = self.window.get_surface()
                surface.set_position(0, self._margin_top)
            except:
                pass
        return False

    def _flush_drag_position(self):
        """Apply pending drag position."""
        self._drag_update_pending = False
        self._margin_top = self._pending_margin
        self._apply_margin_position()
        return False

    def _on_tab_enter(self, controller, x, y):
        """Change cursor to grab hand on hover."""
        self._tab_draw.set_cursor(Gdk.Cursor.new_from_name("grab"))
        return False

    def _on_tab_leave(self, controller):
        """Restore default cursor."""
        self._tab_draw.set_cursor(None)
        return False

    def _on_revealer_animation_done(self, widget, pspec):
        """Move grip to final position after revealer animation completes."""
        self._update_grip_position()

    def _update_grip_position(self):
        """Update grip tab x position based on revealer width."""
        if self._expanded:
            child = self._revealer.get_child()
            if child:
                child.show()
                width = child.get_width()
                self._visual_bg.set_size_request(width + 20, 52)
                if self._icons_bg:
                    self._icons_bg.set_size_request(width, 52)
                self._fixed.move(self._tab_draw, self._revealer_x + width, self._tab_y)
                self._left_grip_draw.set_visible(True)
                self._fixed.move(self._left_grip_draw, 0, self._tab_y)
        else:
            self._left_grip_draw.set_visible(False)
            self._fixed.move(self._tab_draw, 0, self._tab_y)
            self._visual_bg.set_size_request(0, 52)
            if self._icons_bg:
                self._icons_bg.set_size_request(0, 52)

    def _on_draw_left_grip(self, area, cr, width, height, data=None):
        """Draw a rectangular grip pattern on the left side."""
        w, h = width, height

        cr.new_path()
        cr.rectangle(0, 0, w, h)
        cr.close_path()

        bg = _hex_to_rgb(NORD["nord1"])
        cr.set_source_rgb(*bg)
        cr.fill()

        dot_color = _hex_to_rgb(NORD["nord3"])
        cr.set_source_rgb(*dot_color)

        total_dot_rows = 5
        total_height = (total_dot_rows - 1) * GRIP_DOT_SPACING
        start_y = (h - total_height) / 2
        center_x = w / 2

        for row in range(total_dot_rows):
            y = start_y + row * GRIP_DOT_SPACING
            for col in range(GRIP_DOT_COLS):
                offset = (col - (GRIP_DOT_COLS - 1) / 2) * GRIP_DOT_COL_GAP
                x = center_x + offset
                cr.arc(x, y, GRIP_DOT_RADIUS, 0, 2 * math.pi)
                cr.fill()

        return False

    def _on_draw_visual_bg(self, area, cr, width, height, data=None):
        """Draw background with gradient and border."""
        w, h = width, height

        if w <= 0 or h <= 0:
            return True

        grad = cairo.LinearGradient(0, 0, 0, h)
        grad.add_color_stop_rgba(0, 0.15, 0.15, 0.15, 0.95)
        grad.add_color_stop_rgba(1, 0.02, 0.02, 0.02, 0.95)
        cr.set_source(grad)
        cr.paint()

        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w-1, h-1)
        cr.stroke()

        return True

    def _on_left_grip_press(self, controller, n_press, x, y):
        """Record starting position for potential drag."""
        if n_press == 1:
            self._button_pressed = True
            self._is_dragging = False
        return True

    def _on_left_grip_release(self, controller, n_press, x, y):
        """On release of left grip: toggle if click, save if drag."""
        self._button_pressed = False

        if self._is_dragging:
            self._is_dragging = False
            self._save_state()
        else:
            self._expanded = not self._expanded
            self._revealer.set_reveal_child(self._expanded)
            self._update_grip_position()
            self._tab_draw.queue_draw()
            self._save_state()

        return True

    def _refresh_entries(self):
        """Rescan .desktop files, group by category, and rebuild icons if changed."""
        try:
            new_entries = scan_desktop_entries()
        except Exception as e:
            print(f"[mados-launcher] Error scanning desktop entries: {e}")
            return True

        new_names = [e.filename for e in new_entries]
        old_names = [e.filename for e in self._entries]

        if new_names != old_names:
            self._entries = new_entries
            self._grouped = group_entries(new_entries)
            self._rebuild_icons()

        return True

    def _rebuild_icons(self):
        """Clear and rebuild all icon buttons in the dock."""
        child = self._icons_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._icons_box.remove(child)
            child = next_child
        self._icon_buttons.clear()

        for item in self._grouped:
            if isinstance(item, EntryGroup):
                self._build_group_icon(item)
            else:
                self._build_single_icon(item)

        self._icons_box.show()

    def _build_single_icon(self, entry):
        """Build an icon button for a single (ungrouped) entry."""
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item_box.set_size_request(64, 52)

        btn = Gtk.Button()
        btn.add_css_class("launcher-icon")
        btn.set_tooltip_text(entry.name)
        btn.set_size_request(ICON_SIZE + 8, ICON_SIZE + 8)

        image = self._make_icon_image(entry)
        image.set_size_request(ICON_SIZE, ICON_SIZE)
        image.set_name("launcher-image")
        btn.set_child(image)
        btn.connect("clicked", self._on_icon_clicked, entry.exec_cmd, entry.terminal)
        
        # Enter/leave signals for zoom using EventControllerMotion
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("enter", lambda c, x, y: self._on_icon_enter(c, btn, entry))
        motion_controller.connect("leave", lambda c: self._on_icon_leave(c, btn, entry))
        btn.add_controller(motion_controller)

        item_box.append(btn)

        indicator = Gtk.DrawingArea()
        indicator.set_size_request(ICON_SIZE + 8, 4)
        indicator.set_draw_func(self._on_draw_indicator, entry)

        item_box.append(indicator)

        self._icons_box.append(item_box)
        self._icon_buttons.append((btn, indicator, entry, item_box))

    def _build_group_icon(self, group):
        """Build an icon button for a group of entries."""
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item_box.set_size_request(ICON_SIZE + 8, 52)

        btn = Gtk.Button()
        btn.add_css_class("launcher-icon")
        btn.add_css_class("launcher-group")
        btn.set_tooltip_text(f"{group.group_name} ({len(group.entries)})")
        btn.set_size_request(ICON_SIZE + 8, ICON_SIZE + 8)

        image = self._make_icon_image(group.representative)
        image.set_size_request(ICON_SIZE, ICON_SIZE)
        image = self._make_icon_image(group.representative)
        image.set_size_request(ICON_SIZE, ICON_SIZE)
        image.set_name("launcher-image")
        btn.set_child(image)
        btn.connect("clicked", self._on_group_clicked, group)
        
        # Enter/leave signals for zoom using EventControllerMotion
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("enter", lambda c, x, y: self._on_icon_enter(c, btn, group.representative))
        motion_controller.connect("leave", lambda c: self._on_icon_leave(c, btn, group.representative))
        btn.add_controller(motion_controller)

        item_box.append(btn)

        indicator = Gtk.DrawingArea()
        indicator.set_size_request(ICON_SIZE + 8, 4)
        indicator.set_draw_func(self._on_draw_group_indicator, group)

        item_box.append(indicator)

        self._icons_box.append(item_box)
        for entry in group.entries:
            self._icon_buttons.append((btn, indicator, entry, item_box))

    def _make_icon_image(self, entry):
        """Create a Gtk.Image widget from a DesktopEntry's icon."""
        icon_name = entry.icon_name
        
        # If it's an absolute path to a file, try to load it
        if icon_name and os.path.isabs(icon_name) and os.path.isfile(icon_name):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_name, ICON_SIZE, ICON_SIZE, True)
                return Gtk.Image.new_from_pixbuf(pixbuf)
            except Exception:
                pass
        
        # Use icon name for theme lookup (GTK4 handles this properly)
        if icon_name:
            image = Gtk.Image.new_from_icon_name(icon_name)
            image.set_pixel_size(ICON_SIZE)
            return image
        
        # Fallback
        image = Gtk.Image.new_from_icon_name("application-x-executable")
        image.set_pixel_size(ICON_SIZE)
        return image

    def _on_group_clicked(self, button, group):
        """Show a popover listing all entries in the group."""
        self._dismiss_active_popover()

        popover = Gtk.Popover()
        popover.set_parent(button)
        popover.set_position(Gtk.PositionType.RIGHT)
        popover.add_css_class("launcher-popup")
        popover.connect("closed", self._on_popover_closed)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_margin_start(4)
        vbox.set_margin_end(4)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)

        for entry in group.entries:
            row = Gtk.Button()
            row.add_css_class("popup-row")

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.set_margin_start(4)
            hbox.set_margin_end(4)
            hbox.set_margin_top(2)
            hbox.set_margin_bottom(2)

            if entry.icon_name and os.path.isabs(entry.icon_name) and os.path.isfile(entry.icon_name):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(entry.icon_name, ICON_SIZE - 2, ICON_SIZE - 2, True)
                    icon = Gtk.Image.new_from_pixbuf(pixbuf)
                except Exception:
                    icon = Gtk.Image.new_from_icon_name(entry.icon_name or "application-x-executable")
                    icon.set_icon_size(Gtk.IconSize.MENU)
            elif entry.icon_name:
                icon = Gtk.Image.new_from_icon_name(entry.icon_name)
                icon.set_icon_size(Gtk.IconSize.MENU)
            else:
                icon = Gtk.Image.new_from_icon_name("application-x-executable")
                icon.set_icon_size(Gtk.IconSize.MENU)

            hbox.append(icon)

            label = Gtk.Label(label=entry.name)
            label.set_xalign(0)
            label.set_hexpand(True)
            hbox.append(label)

            if self._tracker.is_running(entry.exec_cmd, entry.filename):
                dot = Gtk.Label(label="\u25cf")
                dot.add_css_class("running-dot")
                hbox.append(dot)

            row.set_child(hbox)
            row.connect("clicked", self._on_popover_item_clicked, popover, entry.exec_cmd, entry.terminal)
            vbox.append(row)

        popover.set_child(vbox)
        popover.popup()
        self._active_popover = popover

    def _on_popover_item_clicked(self, button, popover, exec_cmd, terminal=False):
        """Launch app from popover and close it."""
        popover.popdown()
        btn = popover.get_parent()
        self._cancel_zoom_animation(btn)
        launch_application(exec_cmd, terminal)
        self._start_bounce_animation(btn)
        self._schedule_auto_collapse()

    def _on_icon_clicked(self, button, exec_cmd, terminal=False):
        """Launch the clicked application."""
        self._cancel_zoom_animation(button)
        launch_application(exec_cmd, terminal)
        self._start_bounce_animation(button)
        self._schedule_auto_collapse()

    def _cancel_zoom_animation(self, btn):
        """Cancel any running zoom animation on the given button."""
        key = id(btn)
        state = self._zoom_state.get(key)
        if state and state.get("timer"):
            GLib.source_remove(state["timer"])
            del self._zoom_state[key]

    def _start_bounce_animation(self, btn):
        """Start bounce animation on the clicked icon button (MacOS style)."""
        key = id(btn)
        if key in self._bounce_state:
            return

        item_box = None
        for b, indicator, entry, box in self._icon_buttons:
            if b == btn:
                item_box = box
                break

        if not item_box:
            return

        self._bounce_state[key] = {
            "start_time": GLib.get_monotonic_time(),
            "timer": GLib.timeout_add(16, self._bounce_tick, key),
            "btn": btn,
            "item_box": item_box,
            "original_margin": item_box.get_margin_top(),
        }

    def _bounce_tick(self, key):
        """Advance one frame of the bounce animation (macOS style)."""
        state = self._bounce_state.get(key)
        if not state:
            return False

        elapsed = (GLib.get_monotonic_time() - state["start_time"]) / 1000000.0
        
        # Bounce for 3 seconds (until auto-collapse)
        if elapsed > BOUNCE_TOTAL_SECONDS:
            if state.get("timer"):
                GLib.source_remove(state["timer"])
            item_box = state.get("item_box")
            if item_box:
                item_box.set_margin_top(state.get("original_margin", 0))
            del self._bounce_state[key]
            return False
        
        # Multiple bounces: sin wave that repeats every 0.5 seconds (slower)
        # Each bounce goes up then down
        bounce = math.sin(elapsed * math.pi * 2 / 0.5)
        y_offset = -int(bounce * 10)  # 10px jump

        item_box = state.get("item_box")
        if item_box:
            item_box.set_margin_top(y_offset)

        return True

    def _schedule_auto_collapse(self):
        """Auto-collapse the dock 3 seconds after launching an application."""
        if not self._expanded:
            return
        if hasattr(self, "_auto_collapse_id") and self._auto_collapse_id:
            GLib.source_remove(self._auto_collapse_id)
        self._auto_collapse_id = GLib.timeout_add_seconds(3, self._auto_collapse)

    def _auto_collapse(self):
        """Collapse the dock (called from timer)."""
        self._auto_collapse_id = None
        for key, state in list(self._bounce_state.items()):
            if state.get("timer"):
                GLib.source_remove(state["timer"])
        self._bounce_state.clear()

        if self._expanded:
            self._expanded = False
            self._revealer.set_reveal_child(False)
            self._tab_draw.queue_draw()
            self._save_state()
        return False

    def _dismiss_active_popover(self):
        """Close the currently active popover, if any."""
        if self._active_popover:
            try:
                self._active_popover.popdown()
            except (AttributeError, RuntimeError):
                pass
            self._active_popover = None

    def _on_popover_closed(self, popover):
        """Clear active popover reference when it closes."""
        if self._active_popover is popover:
            self._active_popover = None

    def _on_window_button_press(self, controller, n_press, x, y):
        """Dismiss any open popover when clicking on the dock background."""
        self._dismiss_active_popover()
        return False

    def _on_icon_enter(self, controller, widget, entry):
        """Start zoom-in animation when mouse enters an icon button."""
        self._animate_icon_zoom(widget, ICON_ZOOM_SIZE, entry)
        return False

    def _on_icon_leave(self, controller, widget, entry):
        """Start zoom-out animation when mouse leaves an icon button."""
        self._animate_icon_zoom(widget, ICON_SIZE, entry)
        return False

    def _animate_icon_zoom(self, btn, target_size, entry):
        """Begin an animated zoom toward target_size for the given icon button."""
        key = id(btn)
        state = self._zoom_state.get(key)

        if state and state.get("timer"):
            GLib.source_remove(state["timer"])

        current = state["current_size"] if state else ICON_SIZE

        image = btn.get_child()

        self._zoom_state[key] = {
            "current_size": current,
            "target_size": target_size,
            "entry": entry,
            "btn": btn,
            "image": image,
            "timer": GLib.timeout_add(ICON_ZOOM_INTERVAL_MS, self._zoom_tick, key),
        }

    def _zoom_tick(self, key):
        """Advance one frame of the icon zoom animation."""
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
        image = state.get("image")
        if image:
            self._apply_icon_size(image, new_size, state.get("entry"))

        if new_size == target:
            state["timer"] = None
            return False
        return True

    def _apply_icon_size(self, image, size, entry=None):
        """Set the icon image to the given pixel size."""
        if image is None:
            return
        # Use pixel_size for theme icons
        image.set_pixel_size(size)

    def _poll_window_state(self):
        """Poll compositor for window state and update indicators."""
        changed = self._tracker.update()
        if changed:
            self._update_indicators()
        return True

    def _update_indicators(self):
        """Update CSS classes and redraw indicators based on window state."""
        for btn, indicator, entry, _ in self._icon_buttons:
            ctx = btn.get_style_context()
            running = self._tracker.is_running(entry.exec_cmd, entry.filename)
            urgent = self._tracker.is_urgent(entry.exec_cmd, entry.filename)
            focused = self._tracker.is_focused(entry.exec_cmd, entry.filename)

            if running:
                btn.add_css_class("running")
            else:
                btn.remove_css_class("running")

            if urgent:
                btn.add_css_class("urgent")
            else:
                btn.remove_css_class("urgent")

            if focused:
                btn.add_css_class("focused")
            else:
                btn.remove_css_class("focused")

            indicator.queue_draw()

    def _on_draw_indicator(self, area, cr, width, height, entry):
        """Draw a small dot indicator below the icon if the app is running."""
        running = self._tracker.is_running(entry.exec_cmd, entry.filename)
        urgent = self._tracker.is_urgent(entry.exec_cmd, entry.filename)
        focused = self._tracker.is_focused(entry.exec_cmd, entry.filename)

        if not running:
            return False

        cx = width / 2
        cy = height / 2

        if urgent:
            color = _hex_to_rgb(NORD["nord12"])
            radius = INDICATOR_DOT_RADIUS + 0.5
        elif focused:
            color = _hex_to_rgb(NORD["nord8"])
            radius = INDICATOR_DOT_RADIUS + 0.5
        else:
            color = _hex_to_rgb(NORD["nord9"])
            radius = INDICATOR_DOT_RADIUS

        cr.set_source_rgb(*color)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        return False

    def _on_draw_group_indicator(self, area, cr, width, height, group):
        """Draw indicator for a group."""
        any_running = False
        any_urgent = False
        any_focused = False

        for entry in group.entries:
            if self._tracker.is_running(entry.exec_cmd, entry.filename):
                any_running = True
            if self._tracker.is_urgent(entry.exec_cmd, entry.filename):
                any_urgent = True
            if self._tracker.is_focused(entry.exec_cmd, entry.filename):
                any_focused = True

        if not any_running:
            return False

        cx = width / 2
        cy = height / 2

        if any_urgent:
            color = _hex_to_rgb(NORD["nord12"])
            radius = INDICATOR_DOT_RADIUS + 0.5
        elif any_focused:
            color = _hex_to_rgb(NORD["nord8"])
            radius = INDICATOR_DOT_RADIUS + 0.5
        else:
            color = _hex_to_rgb(NORD["nord9"])
            radius = INDICATOR_DOT_RADIUS

        cr.set_source_rgb(*color)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        return False

    def _load_state(self):
        """Load dock position and expanded state from config file."""
        if not os.path.isfile(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            self._margin_top = int(state.get("margin_top", DEFAULT_MARGIN_TOP))
            self._expanded = bool(state.get("expanded", False))
        except Exception:
            pass

    def _save_state(self):
        """Persist dock position and expanded state to config file."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            state = {
                "margin_top": self._margin_top,
                "expanded": self._expanded,
            }
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[mados-launcher] Failed to save state: {e}")

    def _on_destroy(self, widget):
        """Save state and quit."""
        self._save_state()
        Gtk.main_quit()