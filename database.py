"""SQLite database for managing launcher applications."""

import os
import sqlite3
import shutil
import time
from datetime import datetime
from typing import Optional

from logger import log

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    exec_cmd    TEXT NOT NULL,
    icon_name   TEXT,
    comment     TEXT,
    categories  TEXT,
    filename    TEXT UNIQUE NOT NULL,
    terminal    INTEGER DEFAULT 0,
    enabled     INTEGER DEFAULT 1,
    launch_sudo INTEGER DEFAULT 0,
    group_mode  TEXT DEFAULT 'auto',
    group_key   TEXT DEFAULT '',
    allow_auto_group INTEGER DEFAULT 1,
    position    INTEGER DEFAULT 0,
    hidden      INTEGER DEFAULT 0,
    last_updated INTEGER,
    UNIQUE(name, filename)
);

CREATE INDEX IF NOT EXISTS idx_apps_position ON apps(position);
CREATE INDEX IF NOT EXISTS idx_apps_filename ON apps(filename);
CREATE INDEX IF NOT EXISTS idx_apps_enabled ON apps(enabled);
"""


class AppDatabase:
    """SQLite database handler for launcher applications."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        """Ensure the database directory exists."""
        db_dir = os.path.dirname(self._db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _init_db(self):
        """Initialize the database with schema."""
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)
            self._migrate_schema(conn)
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Apply lightweight schema migrations for existing databases."""
        cursor = conn.execute("PRAGMA table_info(apps)")
        columns = {row[1] for row in cursor.fetchall()}
        if "group_mode" not in columns:
            conn.execute("ALTER TABLE apps ADD COLUMN group_mode TEXT DEFAULT 'auto'")
        if "group_key" not in columns:
            conn.execute("ALTER TABLE apps ADD COLUMN group_key TEXT DEFAULT ''")
        if "allow_auto_group" not in columns:
            conn.execute(
                "ALTER TABLE apps ADD COLUMN allow_auto_group INTEGER DEFAULT 1"
            )

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self._db_path)

    def _should_force_sudo(self, name: str, exec_cmd: str) -> bool:
        """Return True when app should always run with sudo by default."""
        text = f"{name} {exec_cmd}".lower()
        return "gufw" in text

    def get_all_apps(self) -> list[dict]:
        """Get all applications ordered by position."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM apps WHERE hidden = 0 ORDER BY position, name"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_enabled_apps(self) -> list[dict]:
        """Get only enabled applications ordered by position."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM apps WHERE enabled = 1 AND hidden = 0 ORDER BY position, name"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_app_by_filename(self, filename: str) -> Optional[dict]:
        """Get an app by its desktop file path."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM apps WHERE filename = ?", (filename,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_app_by_id(self, app_id: int) -> Optional[dict]:
        """Get an app by its ID."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_app(self, entry) -> Optional[int]:
        """Add a new application from a DesktopEntry."""
        max_pos = self._get_max_position()
        now = int(datetime.now().timestamp())
        launch_sudo = 1 if self._should_force_sudo(entry.name, entry.exec_cmd) else 0
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO apps 
                (name, exec_cmd, icon_name, comment, categories, filename, terminal, launch_sudo, group_mode, group_key, allow_auto_group, position, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.name,
                    entry.exec_cmd,
                    entry.icon_name,
                    entry.comment,
                    entry.categories,
                    entry.filename,
                    int(entry.terminal),
                    launch_sudo,
                    "auto",
                    "",
                    1,
                    max_pos + 1,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else None

    def update_app(self, app_id: int, **fields):
        """Update application fields."""
        if not fields:
            return
        fields["last_updated"] = int(datetime.now().timestamp())
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [app_id]
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE apps SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()

    def delete_app(self, app_id: int):
        """Delete an application."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
            conn.commit()

    def hide_app(self, app_id: int):
        """Hide an application (soft delete)."""
        self.update_app(app_id, hidden=1)

    def _get_max_position(self) -> int:
        """Get the maximum position value."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT MAX(position) as max_pos FROM apps")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    def reorder_apps(self, app_ids: list[int]):
        """Bulk update positions from ordered list."""
        with self._get_conn() as conn:
            for position, app_id in enumerate(app_ids):
                conn.execute(
                    "UPDATE apps SET position = ? WHERE id = ?",
                    (position, app_id),
                )
            conn.commit()

    def assign_manual_group(self, source_ids: list[int], target_ids: list[int]):
        """Assign dragged and target apps to the same manual group."""
        all_ids = list(dict.fromkeys(target_ids + source_ids))
        if not all_ids:
            return

        group_key = f"manual-{all_ids[0]}-{int(time.time())}"
        with self._get_conn() as conn:
            for app_id in all_ids:
                conn.execute(
                    "UPDATE apps SET group_mode = 'manual', group_key = ?, allow_auto_group = 1 WHERE id = ?",
                    (group_key, app_id),
                )
            conn.commit()

    def resolve_dock_slots(self, enabled_only: bool = True) -> list[dict]:
        """Resolve apps into dock slots with mixed grouping rules."""
        apps = self.get_enabled_apps() if enabled_only else self.get_all_apps()
        slots = []
        grouped = {}

        for app in apps:
            group_mode = app.get("group_mode") or "auto"
            if group_mode == "none":
                slots.append({"type": "single", "app": app})
                continue

            manual_key = (app.get("group_key") or "").strip()
            if group_mode == "manual" and manual_key:
                key = f"manual:{manual_key.lower()}"
                grouped.setdefault(key, []).append(app)
                continue

            if int(app.get("allow_auto_group", 1)) == 1:
                icon = (app.get("icon_name") or "").strip().lower()
                if icon:
                    key = f"auto:{icon}"
                    grouped.setdefault(key, []).append(app)
                    continue

            slots.append({"type": "single", "app": app})

        for key, members in grouped.items():
            if len(members) <= 1:
                slots.append({"type": "single", "app": members[0]})
            else:
                slots.append(
                    {
                        "type": "group",
                        "group_key": key,
                        "apps": sorted(members, key=lambda item: item["position"]),
                        "representative": sorted(
                            members, key=lambda item: item["position"]
                        )[0],
                    }
                )

        def slot_pos(slot):
            if slot["type"] == "single":
                return slot["app"].get("position", 0)
            return slot["representative"].get("position", 0)

        slots.sort(key=slot_pos)
        return slots

    def sync_from_desktop_files(self, desktop_entries: list) -> tuple[int, int, int]:
        """Sync database with desktop entries. Returns (added, updated, removed)."""
        added = 0
        updated = 0
        existing_filenames = set()

        for entry in desktop_entries:
            existing = self.get_app_by_filename(entry.filename)
            now = int(datetime.now().timestamp())

            if existing is None:
                self.add_app(entry)
                added += 1
            else:
                needs_update = False
                update_fields = {}
                if existing["name"] != entry.name:
                    update_fields["name"] = entry.name
                    needs_update = True
                if existing["exec_cmd"] != entry.exec_cmd:
                    update_fields["exec_cmd"] = entry.exec_cmd
                    needs_update = True
                if existing["icon_name"] != entry.icon_name:
                    update_fields["icon_name"] = entry.icon_name
                    needs_update = True
                if existing["comment"] != entry.comment:
                    update_fields["comment"] = entry.comment
                    needs_update = True
                if existing["terminal"] != int(entry.terminal):
                    update_fields["terminal"] = int(entry.terminal)
                    needs_update = True
                if self._should_force_sudo(entry.name, entry.exec_cmd):
                    if existing.get("launch_sudo", 0) != 1:
                        update_fields["launch_sudo"] = 1
                        needs_update = True

                if needs_update:
                    update_fields["last_updated"] = now
                    self.update_app(existing["id"], **update_fields)
                    updated += 1

            existing_filenames.add(entry.filename)

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, filename FROM apps WHERE hidden = 0")
            all_apps = cursor.fetchall()
            removed = 0
            for row in all_apps:
                if row["filename"] not in existing_filenames:
                    self.hide_app(row["id"])
                    removed += 1

        return (added, updated, removed)

    def backup(self, backup_path: Optional[str] = None):
        """Create a backup of the database."""
        if backup_path is None:
            backup_path = self._db_path + ".bak"
        shutil.copy2(self._db_path, backup_path)
        log.info(f"Database backed up to {backup_path}")
