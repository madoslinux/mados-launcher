"""Nord-themed CSS for the madOS Launcher dock."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

from .config import NORD

THEME_CSS = f"""
/* ===== Global Reset ===== */
* {{
    all: unset;
    -gtk-icon-style: regular;
}}

/* ===== Main Window ===== */
#mados-launcher-window {{
    background-color: transparent;
}}

/* ===== Dock Container ===== */
#dock-container {{
    background-color: transparent;
}}

#dock-bg {{
    background-color: #1a1a1a;
    border-radius: 0 8px 8px 0;
    border: 1px solid #4a4a4a;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 2px 8px rgba(0,0,0,0.3);
}}

#icons-bg {{
    background-color: transparent;
}}

/* ===== Grip Tab ===== */
#grip-tab {{
    background-image: linear-gradient(180deg, rgba(42,42,42,0.9) 0%, rgba(26,26,26,0.9) 100%);
    border-radius: 0 7px 7px 0;
    border: 1px solid rgba(51,51,51,0.8);
    border-left: none;
    min-width: 14px;
    padding: 0;
    transition: background-color 200ms ease;
}}

#grip-tab:hover {{
    background-image: linear-gradient(180deg, rgba(58,58,58,0.95) 0%, rgba(42,42,42,0.95) 100%);
    border-color: rgba(68,68,68,0.9);
}}

/* ===== Left Grip ===== */
#left-grip {{
    background-image: linear-gradient(180deg, rgba(42,42,42,0.9) 0%, rgba(26,26,26,0.9) 100%);
    border: 1px solid rgba(51,51,51,0.8);
    border-left: none;
    min-width: 14px;
    padding: 0;
    transition: background-color 200ms ease;
}}

#left-grip:hover {{
    background-image: linear-gradient(180deg, rgba(58,58,58,0.95) 0%, rgba(42,42,42,0.95) 100%);
    border-color: rgba(68,68,68,0.9);
}}

/* ===== Icons Scroll Area ===== */
#icons-scroll {{
    background-color: transparent;
    padding: 1px 2px;
}}

#icons-scroll scrollbar {{
    background-color: {NORD["nord0"]};
    min-height: 4px;
}}

#icons-scroll scrollbar slider {{
    background-color: {NORD["nord3"]};
    border-radius: 2px;
    min-height: 4px;
    min-width: 20px;
}}

#icons-scroll scrollbar slider:hover {{
    background-color: {NORD["nord9"]};
}}

/* ===== Icons Container ===== */
#icons-box {{
    background-color: transparent;
    padding: 5px;
}}

/* ===== Icon Buttons ===== */
.launcher-icon {{
    background-color: transparent;
    border-radius: 5px;
    padding: 4px;
    margin: 0 2px;
    transition: background-color 200ms ease, box-shadow 200ms ease;
}}

.launcher-icon:hover {{
    background-color: transparent;
}}

.launcher-icon:active {{
    background-color: transparent;
}}

/* ===== Running App Indicator ===== */
.launcher-icon.running {{
    background-color: rgba(59, 66, 82, 0.5);
}}

.launcher-icon.focused {{
    background-color: rgba(67, 76, 94, 0.7);
    box-shadow: 0 0 3px rgba(136, 192, 208, 0.4);
}}

.launcher-icon.urgent {{
    background-color: rgba(191, 97, 106, 0.2);
}}

/* Urgent pulse animation */
@keyframes urgent-pulse {{
    0%   {{ opacity: 1.0; }}
    50%  {{ opacity: 0.5; }}
    100% {{ opacity: 1.0; }}
}}

.launcher-icon.urgent {{
    animation: urgent-pulse 1.5s ease-in-out infinite;
}}

/* ===== Tooltip Styling ===== */
tooltip {{
    background-color: {NORD["nord1"]};
    border: 1px solid {NORD["nord3"]};
    border-radius: 4px;
    padding: 2px 4px;
}}

tooltip label {{
    color: {NORD["nord6"]};
    font-size: 10px;
    font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace;
}}

/* ===== Separator ===== */
#dock-separator {{
    background-color: {NORD["nord3"]};
    min-width: 1px;
    margin: 8px 0;
}}

/* ===== Group Icon Badge ===== */
.launcher-group {{
    border-bottom: 2px solid {NORD["nord9"]};
}}

/* ===== Popup Menu (group submenu via Popover) ===== */
.launcher-popup {{
    background-color: {NORD["nord0"]};
    border: 1px solid {NORD["nord3"]};
    border-radius: 6px;
    padding: 4px;
}}

/* Override popover's default background/arrow */
popover.background.launcher-popup {{
    background-color: {NORD["nord0"]};
    border: 1px solid {NORD["nord3"]};
}}

popover.background.launcher-popup > contents {{
    background-color: {NORD["nord0"]};
    border-radius: 6px;
    padding: 2px;
}}

.popup-row {{
    background-color: transparent;
    color: {NORD["nord4"]};
    padding: 4px 8px;
    border-radius: 4px;
    transition: background-color 150ms ease;
}}

.popup-row:hover {{
    background-color: {NORD["nord2"]};
}}

.popup-row label {{
    color: {NORD["nord4"]};
    font-size: 10px;
    font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace;
}}

.popup-row:hover label {{
    color: {NORD["nord6"]};
}}

.running-dot {{
    color: {NORD["nord8"]};
    font-size: 10px;
}}
"""


def apply_theme():
    """Apply the Nord CSS theme globally to the application."""
    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(THEME_CSS.encode("utf-8"))
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
