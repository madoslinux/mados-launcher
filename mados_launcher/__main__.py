#!/usr/bin/env python3
"""Entry point for madOS Launcher dock."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gio
from mados_launcher.app import LauncherApp


class LauncherApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.mados.launcher", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self.launcher = LauncherApp()
        self.add_window(self.launcher.window)
        self.launcher.window.present()


def main():
    app = LauncherApplication()
    app.run(None)


if __name__ == "__main__":
    main()