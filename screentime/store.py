"""SQLite storage for focus intervals.

Every row always carries an end timestamp. The daemon writes `end = start`
when it opens an interval and pushes `end` forward on every heartbeat, so a
crash leaves a correctly closed row behind and loses at most one heartbeat.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS intervals (
    id      INTEGER PRIMARY KEY,
    app_id  TEXT    NOT NULL,
    start   REAL    NOT NULL,   -- unix epoch seconds (UTC)
    end     REAL    NOT NULL,
    title   TEXT                -- only when track_titles is enabled
);
CREATE INDEX IF NOT EXISTS intervals_start ON intervals(start);
CREATE INDEX IF NOT EXISTS intervals_end ON intervals(end);

CREATE TABLE IF NOT EXISTS apps (
    app_id     TEXT PRIMARY KEY,
    exe        TEXT,            -- executable seen for this app_id, helps name resolution
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Intervals shorter than this are dropped on close (alt-tab flicker).
MIN_INTERVAL = 0.25


class Store:
    def __init__(self, path: Path | str, readonly: bool = False):
        self.path = str(path)
        if readonly:
            # A plain connection with query_only (not mode=ro): read-only opens
            # of a WAL database fail when the daemon has already checkpointed
            # and removed the -wal/-shm files.
            self.db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
            self.db.execute("PRAGMA query_only = 1")
        else:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(SCHEMA)
            self.db.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        self.db.close()

    # -- writes (daemon) ---------------------------------------------------

    def open_interval(self, app_id: str, start: float, title: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO intervals(app_id, start, end, title) VALUES (?, ?, ?, ?)",
            (app_id, start, start, title),
        )
        return cur.lastrowid

    def extend_interval(self, interval_id: int, end: float) -> None:
        self.db.execute(
            "UPDATE intervals SET end = MAX(start, ?) WHERE id = ?", (end, interval_id)
        )

    def close_interval(self, interval_id: int, end: float) -> None:
        self.extend_interval(interval_id, end)
        self.db.execute(
            "DELETE FROM intervals WHERE id = ? AND end - start < ?",
            (interval_id, MIN_INTERVAL),
        )

    def note_app(self, app_id: str, exe: str | None, now: float) -> None:
        self.db.execute(
            """INSERT INTO apps(app_id, exe, first_seen, last_seen) VALUES (?, ?, ?, ?)
               ON CONFLICT(app_id) DO UPDATE SET
                   exe = COALESCE(excluded.exe, apps.exe),
                   last_seen = excluded.last_seen""",
            (app_id, exe, now, now),
        )

    def clamp_future(self, now: float) -> None:
        """Repair rows that end in the future (wall clock was set back)."""
        self.db.execute("UPDATE intervals SET end = MAX(start, ?) WHERE end > ?", (now, now))
        self.db.execute("DELETE FROM intervals WHERE start > ?", (now,))

    def purge_titles(self, before: float) -> int:
        """Forget titles of intervals that ended before `before`."""
        cur = self.db.execute(
            "UPDATE intervals SET title = NULL WHERE title IS NOT NULL AND end < ?", (before,)
        )
        return cur.rowcount

    # -- reads (CLI) -------------------------------------------------------

    def intervals_between(self, start: float, end: float) -> list[tuple[int, str, float, float]]:
        return self.db.execute(
            "SELECT id, app_id, start, end FROM intervals WHERE end > ? AND start < ? ORDER BY start",
            (start, end),
        ).fetchall()

    def app_intervals_between(self, app_id: str, start: float, end: float) -> list[tuple[int, float, float, str | None]]:
        return self.db.execute(
            "SELECT id, start, end, title FROM intervals WHERE app_id = ? AND end > ? AND start < ? ORDER BY start",
            (app_id, start, end),
        ).fetchall()

    def first_start(self) -> float | None:
        row = self.db.execute("SELECT MIN(start) FROM intervals").fetchone()
        return row[0] if row else None

    def app_exes(self) -> dict[str, str]:
        return {a: e for a, e in self.db.execute("SELECT app_id, exe FROM apps") if e}

    def known_apps(self) -> list[tuple[str, str | None, float, float]]:
        return self.db.execute(
            "SELECT app_id, exe, first_seen, last_seen FROM apps ORDER BY last_seen DESC"
        ).fetchall()

    def recent(self, limit: int) -> list[tuple[int, str, float, float, str | None]]:
        return self.db.execute(
            "SELECT id, app_id, start, end, title FROM intervals ORDER BY start DESC LIMIT ?",
            (limit,),
        ).fetchall()
