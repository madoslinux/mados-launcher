"""Main application orchestrator for madOS Launcher dock."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk, GLib

from config import REFRESH_INTERVAL_SECONDS, APP_DB_PATH
from window_manager import WindowManager
from state_manager import StateManager
from dock_instance import DockInstance
from window_tracker import WindowTracker
from database import AppDatabase
from logger import log

WINDOW_POLL_MS = 2000


class LauncherApp:
    """madOS Launcher dock orchestrator."""

    def __init__(self):
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-tooltip-timeout", 0)

        log.info("LauncherApp starting...")

        self._entries = []
        self._grouped = []
        self._dock_instances = []
        self._settings_window = None

        self._state = StateManager()
        state = self._state.load()
        self._margin_top = state["margin_top"]
        self._expanded_per_monitor = state.get("expanded_per_monitor", {})
        self._expanded_default = bool(state.get("expanded", False))

        self._db = AppDatabase(APP_DB_PATH)

        from desktop_entries import scan_and_sync
        scan_and_sync(self._db)

        self._win_mgr = WindowManager(self._margin_top)
        self._tracker = WindowTracker()

        self._build_docks()

        for window in self._win_mgr.get_windows():
            window.show_all()

        for dock in self._dock_instances:
            dock.set_expanded(False)

        GLib.timeout_add_seconds(REFRESH_INTERVAL_SECONDS, self._refresh_entries)
        GLib.timeout_add(WINDOW_POLL_MS, self._poll_window_state)

        log.info("LauncherApp ready")

    def _build_docks(self):
        windows = self._win_mgr.get_windows()
        for i, window in enumerate(windows):
            dock = DockInstance(window, self, i, self._tracker)
            self._dock_instances.append(dock)
            window.connect("destroy", self._on_destroy)

    def get_margin_top(self) -> int:
        return self._margin_top

    def set_margin_top(self, margin: int):
        self._margin_top = margin
        self._win_mgr.set_margin_top(margin)

    def get_window_height(self) -> int:
        return self._win_mgr.get_height()

    def get_screen_height(self) -> int:
        return self._win_mgr.get_screen_height()

    def save_state(self):
        expanded_per_monitor = {
            i: dock.is_expanded() for i, dock in enumerate(self._dock_instances)
        }
        self._state.save(self._margin_top, expanded_per_monitor)

    def dismiss_popovers(self):
        pass

    def get_database(self):
        return self._db

    def open_settings(self):
        from settings_window import SettingsWindow
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self._db, self._on_settings_closed)
        self._settings_window.present()

    def _on_settings_closed(self):
        self._settings_window = None
        for dock in self._dock_instances:
            dock.refresh_icons()

    def _refresh_entries(self):
        from desktop_entries import scan_and_sync
        added, updated, removed = scan_and_sync(self._db)
        if added or updated or removed:
            log.info(f"DB sync: added={added}, updated={updated}, removed={removed}")
        return True

    def _poll_window_state(self):
        changed = self._tracker.update()
        if changed:
            for dock in self._dock_instances:
                dock._refresh_running_indicators()
        return True

    def _on_destroy(self, widget):
        expanded_per_monitor = {
            i: dock.is_expanded() for i, dock in enumerate(self._dock_instances)
        }
        self._state.save(self._margin_top, expanded_per_monitor)
        Gtk.main_quit()
