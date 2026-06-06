"""
utils/storage.py — Persistent JSON storage (favorites, recent, session).
All writes are atomic (write-to-tmp + os.replace) to prevent corruption.

v6 changes:
  • Session now saves: window geometry, last_station (dict), always_on_top,
    search_history (list), notifications_enabled
  • load_session() / save_session() updated accordingly
"""
from __future__ import annotations

import json
import os

from core.config import MAX_RECENT
from utils.logger import log

_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

FAV_FILE     = os.path.join(_ROOT, "favorites.json")
RECENT_FILE  = os.path.join(_ROOT, "recent.json")
SESSION_FILE = os.path.join(_ROOT, "session.json")


def _atomic_write(path: str, data) -> bool:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError as e:
        log(f"Failed to write {path}: {e}", "error")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


# ── Favorites ─────────────────────────────────────────────────────────────────

def load_favorites() -> list[dict]:
    if not os.path.exists(FAV_FILE):
        return []
    try:
        with open(FAV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        if data and isinstance(data[0], str):          # old format upgrade
            return [
                {"name": "Saved Station", "url": u, "logo": "",
                 "country": "", "tags": "", "bitrate": 0, "votes": 0, "codec": ""}
                for u in data if isinstance(u, str) and u
            ]
        return [d for d in data if isinstance(d, dict) and d.get("url")]
    except Exception as e:
        log(f"Could not load favorites: {e}", "warning")
        return []


def save_favorites(data: list[dict]) -> bool:
    return _atomic_write(FAV_FILE, data)


# ── Recently played ───────────────────────────────────────────────────────────

def load_recent() -> list[dict]:
    if not os.path.exists(RECENT_FILE):
        return []
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [d for d in data if isinstance(d, dict) and d.get("url")][:MAX_RECENT]
    except Exception as e:
        log(f"Could not load recent: {e}", "debug")
        return []


def save_recent(data: list[dict]) -> bool:
    return _atomic_write(RECENT_FILE, data[:MAX_RECENT])


def add_to_recent(station: dict, recent: list[dict]) -> list[dict]:
    import time as _time
    url = station.get("url", "")
    if not url:
        return recent
    updated = [s for s in recent if s.get("url") != url]
    entry = dict(station)
    entry["played_at"] = _time.time()
    updated.insert(0, entry)
    return updated[:MAX_RECENT]


# ── Session ───────────────────────────────────────────────────────────────────

_SESSION_DEFAULTS: dict = {
    "volume":                70,
    "last_cat":              "top",
    "eq_preset":             "None",
    "eq_enabled":            False,
    "sort_idx":              0,
    # v6 new fields
    "window_geometry":       None,       # e.g. "1160x760+100+50"
    "always_on_top":         False,
    "last_station":          None,       # full station dict to auto-resume
    "search_history":        [],         # list of recent search strings
    "notifications_enabled": True,
    "mini_pos":              None,       # last mini-player position [x, y]
}


def load_session() -> dict:
    if not os.path.exists(SESSION_FILE):
        return dict(_SESSION_DEFAULTS)
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(_SESSION_DEFAULTS)
        return {**_SESSION_DEFAULTS, **data}
    except Exception as e:
        log(f"Could not load session: {e}", "warning")
        return dict(_SESSION_DEFAULTS)


def save_session(**kwargs) -> bool:
    """
    Save session fields.  Pass any subset of the known keys as keyword args.
    Unknown keys are silently ignored.
    """
    current = load_session()
    for k, v in kwargs.items():
        if k in _SESSION_DEFAULTS:
            current[k] = v
    return _atomic_write(SESSION_FILE, current)
