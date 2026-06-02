"""
SQLite database manager for the notifier.

Tracks seen listings, search run history, and notification logs.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(profile_id, name)
);

CREATE TABLE IF NOT EXISTS seen_listings (
    adid        TEXT    NOT NULL,
    search_id   INTEGER NOT NULL REFERENCES searches(id),
    first_seen  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (adid, search_id)
);

CREATE TABLE IF NOT EXISTS search_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id   INTEGER NOT NULL REFERENCES searches(id),
    run_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    listings_found INTEGER NOT NULL DEFAULT 0,
    new_listings   INTEGER NOT NULL DEFAULT 0,
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id   INTEGER NOT NULL REFERENCES searches(id),
    adid        TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    channel     TEXT    NOT NULL DEFAULT 'telegram'
);
"""


class NotifierDB:
    """Manages the SQLite database for the notifier."""

    def __init__(self, path: str | Path = "searches.db"):
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Profiles ────────────────────────────────────────────────────────

    def ensure_profile(self, name: str) -> int:
        """Return the profile ID, creating it if needed."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO profiles (name) VALUES (?)", (name,)
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM profiles WHERE name = ?", (name,)
        ).fetchone()
        assert row is not None
        return row[0]

    # ── Searches ────────────────────────────────────────────────────────

    def ensure_search(self, profile_name: str, search_name: str) -> int:
        """Return the search ID, creating profile + search if needed."""
        profile_id = self.ensure_profile(profile_name)
        self.conn.execute(
            "INSERT OR IGNORE INTO searches (profile_id, name) VALUES (?, ?)",
            (profile_id, search_name),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM searches WHERE profile_id = ? AND name = ?",
            (profile_id, search_name),
        ).fetchone()
        assert row is not None
        return row[0]

    # ── Seen listings ───────────────────────────────────────────────────

    def is_seen(self, search_id: int, adid: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_listings WHERE search_id = ? AND adid = ?",
            (search_id, adid),
        ).fetchone()
        return row is not None

    def mark_seen(self, search_id: int, adids: list[str]) -> int:
        """Mark multiple adids as seen. Returns count of newly inserted rows."""
        count = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for adid in adids:
            try:
                self.conn.execute(
                    "INSERT INTO seen_listings (search_id, adid, first_seen) "
                    "VALUES (?, ?, ?)",
                    (search_id, adid, now),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass  # already seen
        self.conn.commit()
        return count

    def filter_new(self, search_id: int, adids: list[str]) -> list[str]:
        """Return only the adids that are NOT yet seen for this search."""
        if not adids:
            return []
        placeholders = ",".join("?" for _ in adids)
        rows = self.conn.execute(
            f"SELECT adid FROM seen_listings "
            f"WHERE search_id = ? AND adid IN ({placeholders})",
            (search_id, *adids),
        ).fetchall()
        seen = {r[0] for r in rows}
        return [a for a in adids if a not in seen]

    # ── Search runs ─────────────────────────────────────────────────────

    def last_run_at(self, search_id: int) -> Optional[str]:
        """ISO 8601 timestamp of the last successful run, or None."""
        row = self.conn.execute(
            "SELECT run_at FROM search_runs "
            "WHERE search_id = ? AND error_msg IS NULL "
            "ORDER BY run_at DESC LIMIT 1",
            (search_id,),
        ).fetchone()
        if not row:
            return None
        # Normalize to ISO 8601 (SQLite datetime('now') uses space separator)
        return row[0].replace(" ", "T")

    def log_run(
        self,
        search_id: int,
        listings_found: int = 0,
        new_listings: int = 0,
        error_msg: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO search_runs (search_id, listings_found, new_listings, error_msg) "
            "VALUES (?, ?, ?, ?)",
            (search_id, listings_found, new_listings, error_msg),
        )
        self.conn.commit()

    # ── Notifications ───────────────────────────────────────────────────

    def log_notification(self, search_id: int, adid: str, channel: str = "telegram") -> None:
        self.conn.execute(
            "INSERT INTO notifications (search_id, adid, channel) VALUES (?, ?, ?)",
            (search_id, adid, channel),
        )
        self.conn.commit()

    # ── Stats ───────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return summary statistics."""
        total_seen = self.conn.execute(
            "SELECT COUNT(*) FROM seen_listings"
        ).fetchone()[0]
        total_runs = self.conn.execute(
            "SELECT COUNT(*) FROM search_runs"
        ).fetchone()[0]
        total_notifications = self.conn.execute(
            "SELECT COUNT(*) FROM notifications"
        ).fetchone()[0]
        last_run = self.conn.execute(
            "SELECT MAX(run_at) FROM search_runs"
        ).fetchone()[0]
        return {
            "seen_listings": total_seen,
            "total_runs": total_runs,
            "total_notifications": total_notifications,
            "last_run": last_run,
        }
