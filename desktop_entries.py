"""Scanner and parser for .desktop application entries."""

import os
import re
import shlex
import subprocess
from collections import OrderedDict
from configparser import ConfigParser

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf

from config import EXCLUDED_DESKTOP, EXCLUDED_APP_NAMES, ICON_SIZE, AVAHI_DESKTOP_FILES
import config as _config


# Regex to strip field codes from Exec values (%f, %F, %u, %U, %d, %D, %n, %N, %i, %c, %k, %v, %m)
# Uses a possessive-style pattern (atomic via fixed-width match) to avoid backtracking issues.
_FIELD_CODE_RE = re.compile(r" ?%[fFuUdDnNickvm](?:\s|$)")


def _normalize_app_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return " ".join(cleaned.split())


class DesktopEntry:
    """Represents a parsed .desktop application entry."""

    __slots__ = (
        "name",
        "icon_name",
        "exec_cmd",
        "comment",
        "categories",
        "filename",
        "pixbuf",
        "terminal",
    )

    def __init__(
        self,
        name,
        icon_name,
        exec_cmd,
        comment,
        categories,
        filename,
        pixbuf=None,
        terminal=False,
    ):
        self.name = name
        self.icon_name = icon_name
        self.exec_cmd = exec_cmd
        self.comment = comment
        self.categories = categories
        self.filename = filename
        self.pixbuf = pixbuf
        self.terminal = terminal


class EntryGroup:
    """A group of DesktopEntry items sharing the same icon."""

    __slots__ = ("group_name", "entries", "representative")

    def __init__(self, group_name, entries):
        self.group_name = group_name
        self.entries = entries  # list of DesktopEntry
        self.representative = entries[0]  # icon/pixbuf comes from first entry


def _clean_exec(raw_exec):
    """Remove field codes (%u, %f, etc.) and env prefixes from Exec value."""
    cleaned = _FIELD_CODE_RE.sub("", raw_exec).strip()
    return cleaned


def _resolve_icon(icon_name, size=ICON_SIZE):
    """Resolve an icon name to a GdkPixbuf."""
    if not icon_name:
        return None

    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_name, size, size)
        except Exception:
            return None

    icon_theme = Gtk.IconTheme.get_default()
    try:
        pixbuf = icon_theme.load_icon(icon_name, size, 0)
        return pixbuf
    except Exception:
        return None


def _is_gufw_entry(name: str, filename: str, exec_cmd: str) -> bool:
    text = f"{name} {filename} {exec_cmd}".lower()
    return "gufw" in text


def _is_avahi_running():
    """Check whether avahi-daemon is currently active via systemctl."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "avahi-daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def scan_desktop_entries():
    """Scan standard directories for .desktop files and return sorted list of DesktopEntry."""
    entries = {}
    avahi_active = _is_avahi_running()
    selected_gufw_filename = None

    for directory in _config.DESKTOP_DIRS:
        if not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".desktop"):
                continue
            if fname in EXCLUDED_DESKTOP:
                continue
            if fname in entries:
                continue
            # Hide Avahi entries when the service is not running
            if not avahi_active and fname in AVAHI_DESKTOP_FILES:
                continue

            filepath = os.path.join(directory, fname)
            entry = _parse_desktop_file(filepath, fname)
            if entry:
                if _is_gufw_entry(entry.name, entry.filename, entry.exec_cmd):
                    if selected_gufw_filename is None:
                        selected_gufw_filename = fname
                    elif (
                        fname == "gufw.desktop"
                        and selected_gufw_filename != "gufw.desktop"
                    ):
                        entries.pop(selected_gufw_filename, None)
                        selected_gufw_filename = fname
                    else:
                        continue
                entries[fname] = entry

    # Sort alphabetically by display name
    sorted_entries = sorted(entries.values(), key=lambda e: e.name.lower())
    return sorted_entries


def _parse_desktop_file(filepath, filename):
    """Parse a single .desktop file and return a DesktopEntry or None."""
    parser = ConfigParser(interpolation=None, strict=False)
    parser.optionxform = lambda x: x  # Preserve case of keys

    try:
        parser.read(filepath, encoding="utf-8")
    except Exception:
        return None

    section = "Desktop Entry"
    if not parser.has_section(section):
        return None

    def get(key, default=""):
        return parser.get(section, key, fallback=default)

    # Filter out non-application entries
    entry_type = get("Type")
    if entry_type != "Application":
        return None

    # Skip hidden or no-display entries
    if get("NoDisplay", "false").lower() == "true":
        return None
    if get("Hidden", "false").lower() == "true":
        return None

    # Must have Exec
    raw_exec = get("Exec")
    if not raw_exec:
        return None

    name = get("Name", filename)
    if _normalize_app_name(name) in EXCLUDED_APP_NAMES:
        return None
    icon_name = get("Icon", "")
    comment = get("Comment", "")
    categories = get("Categories", "")
    exec_cmd = _clean_exec(raw_exec)
    terminal = get("Terminal", "false").lower() == "true"

    # Resolve icon
    pixbuf = _resolve_icon(icon_name)

    return DesktopEntry(
        name=name,
        icon_name=icon_name,
        exec_cmd=exec_cmd,
        comment=comment,
        categories=categories,
        filename=filename,
        pixbuf=pixbuf,
        terminal=terminal,
    )


def launch_application(exec_cmd, terminal=False):
    """Launch an application from its Exec command string."""
    try:
        args = shlex.split(exec_cmd)
        if terminal:
            terminal_cmd = _config.TERMINAL_CMD.split()
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
        print(f"[mados-launcher] Failed to launch '{exec_cmd}': {e}")


def _icon_group_key(entry):
    """Return the grouping key for an entry based on its icon name.

    Entries with the same icon_name (normalized) will be grouped together.
    Entries with no icon or the generic fallback icon are not grouped.
    """
    icon = (entry.icon_name or "").strip()
    if not icon:
        return None
    # Normalize: lowercase, strip path and extension for comparison
    key = os.path.basename(icon).lower()
    key = os.path.splitext(key)[0] if "." in key else key
    # Don't group under generic fallback icons
    if key in ("application-x-executable", "application-default-icon", "exec", ""):
        return None
    return key


def group_entries(entries):
    """Group entries that share the same icon into a single dock slot.

    Returns a list of items where each item is either:
    - A single DesktopEntry (unique icon), or
    - An EntryGroup (2+ entries sharing the same icon).

    Items are sorted alphabetically: groups by first entry name, singles by name.
    """
    icon_groups = OrderedDict()  # icon_key -> [DesktopEntry]
    ungrouped = []

    for entry in entries:
        key = _icon_group_key(entry)
        if key:
            icon_groups.setdefault(key, []).append(entry)
        else:
            ungrouped.append(entry)

    result = []

    # Groups with 2+ entries become EntryGroup; singletons stay as DesktopEntry
    for icon_key, members in icon_groups.items():
        if len(members) >= 2:
            group_name = members[0].name  # Use first entry's name as label
            result.append(EntryGroup(group_name, members))
        else:
            result.append(members[0])

    # Add ungrouped entries
    result.extend(ungrouped)

    # Sort alphabetically
    def sort_key(item):
        if isinstance(item, EntryGroup):
            return item.representative.name.lower()
        return item.name.lower()

    result.sort(key=sort_key)
    return result


def scan_and_sync(db):
    """Scan desktop entries and sync with database. Returns (added, updated, removed)."""
    entries = scan_desktop_entries()
    return db.sync_from_desktop_files(entries)
