#!/usr/bin/env python3
"""Entry point for madOS Launcher dock."""

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk
from app import LauncherApp


def main():
    """Launch the madOS dock application."""
    if not Gtk.init_check():
        print("Failed to initialize GTK")
        return
    LauncherApp()
    Gtk.main()


if __name__ == "__main__":
    main()
