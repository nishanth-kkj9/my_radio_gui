"""
services/station_service.py — Station fetching with TTL cache and background preload.

FIX: fetch_category() now waits behind a condition variable while the same
category is already being fetched, eliminating duplicate concurrent network
requests for a category.
"""

from __future__ import annotations

import threading, time
from concurrent.futures import ThreadPoolExecutor

from core.api import fetch_stations, fetch_stations_by_tag
from core.config import MAX_RESULTS, QUERY_MAP, PRELOAD_CATEGORIES, CACHE_TTL
from utils.logger import log

_cache:      dict[str, tuple[float, list[dict]]] = {}
_cache_lock  = threading.Lock()
_cache_cv    = threading.Condition(_cache_lock)
_fetching:   set[str] = set()


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

    v13: concurrent callers for the same category wait behind a real
    condition variable instead of all fetching the same network payload.
    """
    fresh: list[dict] = []

    with _cache_cv:
        if use_cache and category in _cache:
            ts, cached = _cache[category]
            if time.time() - ts < CACHE_TTL:
                log(f"Cache hit '{category}' ({len(cached)} stations)", "debug")
                return cached.copy()

        while category in _fetching:
            _cache_cv.wait()

        if use_cache and category in _cache:
            ts, cached = _cache[category]
            if time.time() - ts < CACHE_TTL:
                log(f"Cache hit '{category}' after wait ({len(cached)} stations)", "debug")
                return cached.copy()

        _fetching.add(category)

    fetch_ok = False
    try:
        fresh = _fetch_fresh(category)
        fetch_ok = True
    except Exception as e:
        log(f"fetch_category failed '{category}': {e}", "error")

    with _cache_cv:
        _fetching.discard(category)
        if fetch_ok:
            if fresh:
                _cache[category] = (time.time(), fresh.copy())
            elif category not in _cache or not use_cache:
                _cache.pop(category, None)
        _cache_cv.notify_all()

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
