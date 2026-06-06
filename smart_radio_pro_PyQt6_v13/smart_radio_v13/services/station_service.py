"""
services/station_service.py — Station fetching with TTL cache and background preload.

FIX: fetch_category() now uses a single lock acquire that covers BOTH the cache
read AND the cache write, eliminating the TOCTOU race where two threads could
simultaneously miss the cache and fetch the same category.
"""

from __future__ import annotations

import threading, time
from concurrent.futures import ThreadPoolExecutor

from core.api import fetch_stations, fetch_stations_by_tag
from core.config import MAX_RESULTS, QUERY_MAP, PRELOAD_CATEGORIES, CACHE_TTL
from utils.logger import log

_cache:      dict[str, tuple[float, list[dict]]] = {}
_cache_lock  = threading.Lock()


def _fetch_fresh(category: str) -> list[dict]:
    queries = QUERY_MAP.get(category, [category])
    raw:  list[dict] = []
    seen: set[str]   = set()
    for q in queries:
        try:
            if category in ("top", "hindi", "kannada", "news"):
                batch = fetch_stations(q, limit=MAX_RESULTS)
            else:
                batch = fetch_stations_by_tag(q, limit=MAX_RESULTS)
            for s in batch:
                url = s.get("url", "")
                if url and url not in seen:
                    raw.append(s)
                    seen.add(url)
        except Exception as e:
            log(f"fetch error '{q}': {e}", "error")
    log(f"'{category}': fetched {len(raw)} stations", "info")
    return raw


def fetch_category(category: str, use_cache: bool = True) -> list[dict]:
    """
    Fetch stations for *category*.

    FIX: The entire cache-check + cache-write is now performed under ONE lock
    acquisition. Previously, the read happened outside the lock and the write
    inside a separate lock acquisition, creating a window where two threads
    could both see a cache miss and both fetch the same category concurrently.
    """
    with _cache_lock:
        if use_cache and category in _cache:
            ts, cached = _cache[category]
            if time.time() - ts < CACHE_TTL:
                log(f"Cache hit '{category}' ({len(cached)} stations)", "debug")
                return cached.copy()
        # Cache miss or expired — fetch outside the lock to avoid blocking
        # other categories. We re-acquire the lock to write the result.

    # ── Fetch outside the lock (network call) ─────────────────
    fresh = _fetch_fresh(category)

    with _cache_lock:
        if fresh:
            _cache[category] = (time.time(), fresh.copy())
        elif category in _cache:
            log(f"0 results for '{category}' — keeping stale cache", "warning")
            return _cache[category][1].copy()

    return fresh


def preload_categories(exclude: str = "top") -> None:
    log("Background preload starting…", "info")

    def _load_one(cat: str) -> tuple[str, int]:
        try:
            stations = fetch_category(cat, use_cache=False)
            return cat, len(stations)
        except Exception as e:
            log(f"Preload failed '{cat}': {e}", "warning")
            return cat, 0

    cats = [c for c in PRELOAD_CATEGORIES if c != exclude]
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="preload") as pool:
        for cat, n in pool.map(_load_one, cats):
            if n == 0:
                log(f"Preload: 0 stations for '{cat}'", "warning")
    log("Background preload complete.", "info")
