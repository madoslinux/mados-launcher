# AGENTS.md - madOS Launcher Development Guide

## Project Overview

madOS Launcher is a GTK3-based application dock for Wayland compositors (Sway/Hyprland). It provides a retractable icon dock anchored to the left edge of the screen with running app indicators.

## Build, Lint, and Test Commands

### Running the Application

```bash
# Run directly with Python
python3 -m mados_launcher

# Or use the module entry point
python3 -m mados_launcher
```

### Dependencies

The project requires:
- Python 3.x
- GTK3 (gir1.2-gtk-3.0)
- GdkPixbuf (gir1.2-gdkpixbuf-2.0)
- gtk-layer-shell (optional, for Wayland layer shell support)
- Sway or Hyprland compositor

### Testing

**No test framework is currently configured.** To run tests in the future:

```bash
# With pytest
python3 -m pytest

# Run a single test file
python3 -m pytest tests/test_desktop_entries.py

# Run a specific test
python3 -m pytest tests/test_desktop_entries.py::test_scan_desktop_entries -v
```

### Linting

No linting tools are configured. To add linting, consider:

```bash
# With ruff
ruff check .

# With pylint
python3 -m pylint mados_launcher/

# With mypy (type checking)
python3 -m mypy .
```

### Type Checking

No type checking is configured. Consider adding mypy for type hints validation.

## Code Style Guidelines

### General Philosophy

- Keep code simple and readable
- Avoid premature abstraction
- Use explicit over implicit
- No comments unless they explain "why", not "what"

### Imports

**Order (each group separated by blank line):**
1. Standard library
2. Third-party (gi, etc.)
3. Local relative imports

```python
import json
import math
import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from . import __app_id__, __app_name__
from .config import NORD, ICON_SIZE
from .desktop_entries import scan_desktop_entries
```

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `LauncherApp`, `DesktopEntry`)
- **Functions/variables**: `snake_case` (e.g., `scan_desktop_entries`, `icon_size`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `ICON_SIZE`, `NORD`)
- **Private methods**: prefix with `_` (e.g., `_build_window`)
- **Private variables**: prefix with `_` (e.g., `self._expanded`)

### Type Hints

Use type hints where they improve readability. Not strictly required but encouraged:

```python
def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color string to (r, g, b) floats 0-1."""
    ...

def scan_desktop_entries() -> list[DesktopEntry]:
    """Scan standard directories for .desktop files."""
    ...
```

### Classes

- Use `__slots__` for simple data classes to reduce memory:
  ```python
  class DesktopEntry:
      __slots__ = ("name", "icon_name", "exec_cmd", "comment", "categories", "filename", "pixbuf")
  ```
- Use dataclasses or attrs if more features are needed

### Error Handling

- Use specific exception types when possible
- Return early with defaults for expected failures
- Log errors with informative messages:
  ```python
  try:
      # operation that might fail
  except Exception as e:
      print(f"[mados-launcher] Error scanning desktop entries: {e}")
      return True  # Keep timeout alive
  ```

### Docstrings

Use Google-style or simple docstrings for public APIs:

```python
class LauncherApp:
    """madOS Launcher dock — a retractable icon dock anchored to the left edge."""

    def _build_window(self):
        """Create the GTK window and configure it as a layer-shell surface."""
```

### GTK Patterns

- Use `connect("signal-name", callback)` for signal handlers
- Return `True` to stop event propagation, `False` to let it propagate
- Use `GLib.timeout_add()` for periodic tasks
- Use `GLib.idle_add()` for deferred UI updates

### Window Tracker

The `WindowTracker` class queries compositor IPC (swaymsg/hyprctl) to detect running applications. It supports:
- Sway via `swaymsg -t get_tree`
- Hyprland via `hyprctl clients -j`

### CSS/Theming

Theme is defined in `theme.py` as a Python f-string with Nord color palette. Colors are imported from `config.py` which defines the NORD dictionary.

### State Persistence

- Store state in `~/.config/mados-launcher/state.json`
- Use JSON for serialization
- Handle missing/corrupt state gracefully

### Performance Considerations

- Use `__slots__` on data classes
- Throttle drag position updates with `GLib.idle_add()`
- Use `GLib.source_remove()` to cancel timers
- Reuse pixbuf instances where possible

### Common Patterns

**Optional dependency (gtk-layer-shell):**
```python
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False
```

**Periodic task:**
```python
GLib.timeout_add_seconds(REFRESH_INTERVAL_SECONDS, self._refresh_entries)
```

**Animation frame:**
```python
GLib.timeout_add(16, self._bounce_tick, key)  # ~60fps
```

## File Structure

```
mados-launcher/
├── __init__.py          # Package info (version, app_id)
├── __main__.py          # Entry point
├── app.py               # Main LauncherApp class
├── config.py            # Configuration constants
├── desktop_entries.py   # .desktop file parsing
├── theme.py             # CSS theming (Nord palette)
├── window_tracker.py    # Sway/Hyprland IPC integration
├── AGENTS.md            # This file
```

## Adding New Features

1. Follow the existing code patterns
2. Add configuration to `config.py` if needed
3. Keep the Nord color scheme consistent
4. Test on both Sway and Hyprland if compositor-related
5. Handle missing dependencies gracefully