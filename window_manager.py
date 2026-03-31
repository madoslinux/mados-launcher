"""Window management with gtk-layer-shell support and fallback."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk

from __init__ import __app_id__, __app_name__
from config import DEFAULT_MARGIN_TOP
from logger import log

HAS_LAYER_SHELL = False
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell

    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    GtkLayerShell = None


class WindowManager:
    """Manages the dock windows with gtk-layer-shell - one per monitor."""

    def __init__(self, margin_top: int = DEFAULT_MARGIN_TOP):
        self._margin_top = margin_top
        self._screen_height = 768
        self._window_height = 150
        self._windows = []

        self._create_windows_for_monitors()
        self._get_screen_dimensions()

    def _create_windows_for_monitors(self):
        """Create a dock window for each monitor."""
        display = Gdk.Display.get_default()
        if not display:
            log.error("No display available")
            return

        monitor_count = display.get_n_monitors()
        log.info(f"Creating dock for {monitor_count} monitor(s)")

        for i in range(monitor_count):
            monitor = display.get_monitor(i)
            if not monitor:
                continue

            window = self._create_window_for_monitor(monitor, i)
            if window:
                self._windows.append(window)

        if not self._windows:
            log.error("Failed to create any dock windows")

    def _create_window_for_monitor(self, monitor, index: int) -> Gtk.Window:
        """Create a dock window for a specific monitor."""
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        window.set_title(f"{__app_name__} {index}")
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_name("mados-launcher-window")
        window.set_size_request(150, 150)

        screen = window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            window.set_visual(visual)
        window.set_app_paintable(True)

        if HAS_LAYER_SHELL:
            display = Gdk.Display.get_default()
            GtkLayerShell.init_for_window(window)
            GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_namespace(window, f"{__app_id__}-{index}")

            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, False)
            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.BOTTOM, False)

            GtkLayerShell.set_monitor(window, monitor)

            GtkLayerShell.set_exclusive_zone(window, 0)
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, self._margin_top)
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.LEFT, 0)
            GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
        else:
            geom = monitor.get_geometry()
            window.set_type_hint(Gdk.WindowTypeHint.DOCK)
            window.set_keep_above(True)
            window.set_skip_taskbar_hint(True)
            window.set_skip_pager_hint(True)
            window.stick()
            window.move(0, self._margin_top)

        return window

    def _get_screen_dimensions(self):
        """Get screen dimensions for drag clamping."""
        display = Gdk.Display.get_default()
        if display:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            if monitor:
                geom = monitor.get_geometry()
                self._screen_height = geom.height

    def set_margin_top(self, margin: int):
        """Set the top margin (vertical position) for all windows."""
        self._margin_top = margin
        for window in self._windows:
            if HAS_LAYER_SHELL:
                GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, margin)
            else:
                window.move(0, margin)

    def get_margin_top(self) -> int:
        """Get current top margin."""
        return self._margin_top

    def get_height(self) -> int:
        """Get window height."""
        return self._window_height

    def get_screen_height(self) -> int:
        """Get screen height."""
        return self._screen_height

    def get_windows(self) -> list[Gtk.Window]:
        """Get all dock windows."""
        return self._windows

    def get_window(self) -> Gtk.Window:
        """Get the first dock window (for backwards compatibility)."""
        return self._windows[0] if self._windows else None

    def connect_destroy(self, callback):
        """Connect destroy signal to all windows."""
        for window in self._windows:
            window.connect("destroy", callback)
