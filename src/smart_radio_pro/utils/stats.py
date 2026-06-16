"""
utils/stats.py — Per-station playback statistics (v6).

Tracks: play_count, total_seconds, last_played per station URL.
Persists to stats.json via atomic writes. Thread-safe.

Public API:
    record_play(url, name)             → None
    record_listen_time(url, seconds)   → None
    get_play_count(url)                → int
    get_most_played(limit)             → list[dict]
    get_total_listen_time()            → int   (total seconds all time)
    get_today_listen_time()            → int   (seconds today)
    clear()                            → None
"""
from __future__ import annotations

import json
import os
import threading
import time

from smart_radio_pro.utils.logger import log

_ROOT      = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STATS_FILE = os.path.join(_ROOT, "stats.json")

_lock:  threading.Lock = threading.Lock()
_cache: dict | None    = None   # {url: {name, play_count, total_seconds, last_played}}
_today: float          = 0.0    # seconds listened today (in-memory only, resets on launch)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if not os.path.exists(STATS_FILE):
        _cache = {}
        return _cache
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _cache = raw if isinstance(raw, dict) else {}
    except Exception as e:
        log(f"Stats load error: {e}", "warning")
        _cache = {}
    return _cache


def _save(data: dict) -> None:
    tmp = STATS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, STATS_FILE)
    except Exception as e:
        log(f"Stats save failed: {e}", "warning")
        try:
            os.remove(tmp)
        except OSError:
            pass


# ── Public API ────────────────────────────────────────────────────────────────

def record_play(url: str, name: str) -> None:
    """Increment play count for a station URL."""
    if not url:
        return
    with _lock:
        data  = _load()
        entry = data.get(url, {"name": name, "play_count": 0, "total_seconds": 0})
        entry["name"]        = name
        entry["play_count"]  = entry.get("play_count", 0) + 1
        entry["last_played"] = time.time()
        data[url] = entry
        _save(data)


def record_listen_time(url: str, seconds: int) -> None:
    """Add *seconds* of listening time to a station's total. Minimum 5 s."""
    global _today
    if seconds < 5 or not url:
        return
    with _lock:
        data = _load()
        if url in data:
            data[url]["total_seconds"] = data[url].get("total_seconds", 0) + seconds
            _save(data)
        _today += seconds


def get_play_count(url: str) -> int:
    with _lock:
        return _load().get(url, {}).get("play_count", 0)


def get_total_seconds(url: str) -> int:
    """Total seconds listened to a specific station URL."""
    with _lock:
        return _load().get(url, {}).get("total_seconds", 0)


def get_most_played(limit: int = 10) -> list[dict]:
    """Return top *limit* stations sorted by play_count descending."""
    with _lock:
        data = _load()
    entries = [{"url": k, **v} for k, v in data.items() if isinstance(v, dict)]
    return sorted(entries, key=lambda x: x.get("play_count", 0), reverse=True)[:limit]


def get_total_listen_time() -> int:
    """Total seconds listened across all stations (all-time)."""
    with _lock:
        data = _load()
    return sum(v.get("total_seconds", 0) for v in data.values() if isinstance(v, dict))


def get_today_listen_time() -> int:
    """Seconds listened since app launch (resets each session)."""
    return int(_today)


def clear() -> None:
    """Wipe all statistics."""
    global _cache, _today
    with _lock:
        _cache = {}
        _today = 0.0
        _save({})
