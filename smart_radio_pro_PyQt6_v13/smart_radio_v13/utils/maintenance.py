"""utils/maintenance.py — Startup integrity checks and cache helpers."""

import os, json
from utils.logger import log
from utils.storage import FAV_FILE


def check_favorites_integrity() -> bool:
    if not os.path.exists(FAV_FILE):
        return True
    try:
        with open(FAV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, list)
    except Exception as e:
        log(f"Favorites integrity check failed: {e}", "warning")
        return False


def purge_mem_logo_cache(cache: dict, keys: list, max_size: int):
    """Evict oldest entries from the in-memory PhotoImage cache. Call with lock held."""
    while len(cache) > max_size and keys:
        cache.pop(keys.pop(0), None)
