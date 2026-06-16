"""
utils/logo_cache.py — Persistent SQLite logo cache.

Design:
  • Logos are downloaded once and stored as PNG bytes in a local SQLite DB.
  • On subsequent launches the logo is served from disk — zero network cost.
  • Each entry has a `cached_at` timestamp; entries older than LOGO_DB_TTL_DAYS
    are evicted when the DB exceeds LOGO_DB_MAX_ENTRIES (vacuum on startup).
  • Thread-safe: every public method opens its own short-lived connection with
    check_same_thread=False and WAL journal mode for concurrent readers.

Schema:
    logos(url TEXT PK, size INT, data BLOB, cached_at REAL)

Public API:
    get(url, size)           → bytes | None
    put(url, size, data)     → None
    vacuum()                 → None   (called at startup in background thread)
    stats()                  → dict   (url_count, total_bytes)
"""

from __future__ import annotations

import sqlite3
import threading
import time
import os

from smart_radio_pro.core.config import LOGO_DB_MAX_ENTRIES, LOGO_DB_TTL_DAYS
from smart_radio_pro.utils.logger import log

_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
DB_PATH = os.path.join(_ROOT, "logos.db")

_init_lock = threading.Lock()
_initialized = False


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _ensure_schema():
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        with _conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS logos (
                    url       TEXT    NOT NULL,
                    size      INTEGER NOT NULL,
                    data      BLOB    NOT NULL,
                    cached_at REAL    NOT NULL,
                    PRIMARY KEY (url, size)
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS logos_ts ON logos(cached_at)")
        _initialized = True
        log(f"Logo DB ready: {DB_PATH}", "debug")


def get(url: str, size: int) -> bytes | None:
    """Return cached PNG bytes for (url, size), or None if not cached."""
    _ensure_schema()
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT data FROM logos WHERE url=? AND size=?", (url, size)
            ).fetchone()
            return row[0] if row else None
    except Exception as e:
        log(f"Logo DB get error: {e}", "warning")
        return None


def put(url: str, size: int, data: bytes) -> None:
    """Store PNG bytes for (url, size). Silently overwrites existing entry."""
    _ensure_schema()
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO logos(url, size, data, cached_at) VALUES(?,?,?,?)",
                (url, size, data, time.time()),
            )
    except Exception as e:
        log(f"Logo DB put error: {e}", "warning")


def vacuum() -> None:
    """
    Remove stale / excess logos. Run once at startup in a background thread.
      1. Delete entries older than LOGO_DB_TTL_DAYS.
      2. If still over LOGO_DB_MAX_ENTRIES, delete the oldest excess.
      3. Run SQLite VACUUM to reclaim disk space.
    """
    _ensure_schema()
    try:
        cutoff = time.time() - LOGO_DB_TTL_DAYS * 86400
        with _conn() as c:
            deleted_old = c.execute(
                "DELETE FROM logos WHERE cached_at < ?", (cutoff,)
            ).rowcount
            count = c.execute("SELECT COUNT(*) FROM logos").fetchone()[0]
            deleted_excess = 0
            if count > LOGO_DB_MAX_ENTRIES:
                excess = count - LOGO_DB_MAX_ENTRIES
                c.execute(
                    "DELETE FROM logos WHERE rowid IN "
                    "(SELECT rowid FROM logos ORDER BY cached_at ASC LIMIT ?)",
                    (excess,),
                )
                deleted_excess = excess
        if deleted_old or deleted_excess:
            with _conn() as c:
                c.execute("VACUUM")
            log(f"Logo DB vacuum: removed {deleted_old} stale + "
                f"{deleted_excess} excess entries", "info")
        else:
            log("Logo DB vacuum: nothing to remove", "debug")
    except Exception as e:
        log(f"Logo DB vacuum error: {e}", "warning")


def stats() -> dict:
    """Return {count, total_bytes} for the logo DB."""
    _ensure_schema()
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(data)),0) FROM logos"
            ).fetchone()
            return {"count": row[0], "total_bytes": row[1]}
    except Exception:
        return {"count": 0, "total_bytes": 0}
