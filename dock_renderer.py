"""Cairo rendering for dock visual elements: background, grips, indicators."""

import cairo
import math

from config import (
    NORD,
    TAB_WIDTH,
    TAB_HEIGHT,
    GRIP_DOT_RADIUS,
    GRIP_DOT_SPACING,
    GRIP_DOT_COLS,
    GRIP_DOT_COL_GAP,
)


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to (r, g, b) floats 0-1."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


class DockRenderer:
    """Cairo rendering for dock visual elements."""

    def __init__(self):
        self._tab_y = (150 - TAB_HEIGHT) // 2

    @property
    def tab_y(self) -> int:
        return self._tab_y

    def draw_background(self, cr, width: int, height: int):
        """Draw background with black 85% opacity and border."""
        cr.set_source_rgba(0, 0, 0, 0.85)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        cr.set_source_rgb(0.25, 0.25, 0.25)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()

    def draw_grip_tab(self, cr, x: int, y: int, w: int, h: int, expanded: bool):
        """Draw the grip tab with dots and chevron."""
        radius = 8

        cr.new_path()
        cr.move_to(x, y)
        cr.line_to(x + w - radius, y)
        cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
        cr.line_to(x + w, y + h - radius)
        cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
        cr.line_to(x, y + h)
        cr.close_path()

        bg = hex_to_rgb(NORD["nord1"])
        cr.set_source_rgb(*bg)
        cr.fill()

        dot_color = hex_to_rgb(NORD["nord3"])
        cr.set_source_rgb(*dot_color)

        total_dot_rows = 5
        total_height = (total_dot_rows - 1) * GRIP_DOT_SPACING
        start_y = y + (h - total_height) / 2
        center_x = x + w / 2

        for row in range(total_dot_rows):
            dy = start_y + row * GRIP_DOT_SPACING
            for col in range(GRIP_DOT_COLS):
                offset = (col - (GRIP_DOT_COLS - 1) / 2) * GRIP_DOT_COL_GAP
                dx = center_x + offset
                cr.arc(dx, dy, GRIP_DOT_RADIUS, 0, 2 * math.pi)
                cr.fill()

        chevron_color = hex_to_rgb(NORD["nord9"])
        cr.set_source_rgba(*chevron_color, 0.6)
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        chevron_y = y + h - 14
        cx = x + w / 2

        if expanded:
            cr.move_to(cx + 3, chevron_y - 4)
            cr.line_to(cx - 2, chevron_y)
            cr.line_to(cx + 3, chevron_y + 4)
        else:
            cr.move_to(cx - 3, chevron_y - 4)
            cr.line_to(cx + 2, chevron_y)
            cr.line_to(cx - 3, chevron_y + 4)

        cr.stroke()

    def draw_left_grip(self, cr, x: int, y: int, w: int, h: int):
        """Draw the left grip (visible when expanded)."""
        cr.new_path()
        cr.rectangle(x, y, w, h)
        cr.close_path()

        bg = hex_to_rgb(NORD["nord1"])
        cr.set_source_rgb(*bg)
        cr.fill()

        dot_color = hex_to_rgb(NORD["nord3"])
        cr.set_source_rgb(*dot_color)

        total_dot_rows = 5
        total_height = (total_dot_rows - 1) * GRIP_DOT_SPACING
        start_y = y + (h - total_height) / 2
        center_x = x + w / 2

        for row in range(total_dot_rows):
            dy = start_y + row * GRIP_DOT_SPACING
            for col in range(GRIP_DOT_COLS):
                offset = (col - (GRIP_DOT_COLS - 1) / 2) * GRIP_DOT_COL_GAP
                dx = center_x + offset
                cr.arc(dx, dy, GRIP_DOT_RADIUS, 0, 2 * math.pi)
                cr.fill()
