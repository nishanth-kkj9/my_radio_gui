"""
utils/logo_loader.py — Shared logo download, caching, and processing (v13).

Consolidates the duplicated logo-loading logic that previously existed in
_load_logo(), _load_thumb_logo(), and _load_mini_logo() across the UI layer
into a single, reusable utility.

Public API:
    submit_logo_load(url, size, session, failed_set, executor, logo_ready_signal,
                     card_ref, default_pixmap, mem_cache, mem_keys, mem_lock, max_mem_entries)
        → submits a background task that:
            1. Checks SQLite persistent cache
            2. Downloads from network (using shared session for connection pooling)
            3. Resizes + applies circular mask
            4. Writes to SQLite cache for future launches
            5. Stores in in-memory cache
            6. Emits logo_ready_signal with the result

    process_logo_bytes(raw_bytes, size) -> Image.Image | None
        Resizes and masks raw image bytes.
"""

from __future__ import annotations

import io
import threading
from typing import Any, Optional

from PIL import Image, ImageDraw
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPixmap

from core.config import LOGO_MAX_BYTES, LOGO_TIMEOUT
from utils.logger import log
from utils.logo_cache import get as db_logo_get, put as db_logo_put
from utils.maintenance import purge_mem_logo_cache


def _pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert a PIL Image to a QPixmap."""
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue())
    return pixmap


def process_logo_bytes(raw_bytes: bytes, size: int) -> Optional[Image.Image]:
    """
    Decode raw image bytes, resize to *size*×*size*, and apply a circular mask.

    Returns the processed PIL Image, or None on failure.
    """
    try:
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((1, 1, size - 1, size - 1), fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        return out
    except Exception as e:
        log(f"Logo processing error: {e}", "debug")
        return None


def submit_logo_load(
    url: str,
    size: int,
    session: Any,
    failed_set: set,
    executor: Any,
    logo_ready_signal: pyqtSignal,
    card_ref: QObject,
    default_pixmap: QPixmap,
    mem_cache: dict,
    mem_keys: list,
    mem_lock: threading.Lock,
    max_mem_entries: int,
) -> None:
    """
    Submit a background task to load, cache, and deliver a station logo.

    This replaces the three duplicated logo-loading methods
    (_load_logo, _load_thumb_logo, _load_mini_logo) with a single path.

    Parameters:
        url                 — Logo URL to load.
        size                — Desired logo size in px (e.g. LOGO_SZ, THUMB_SZ, MINI_LOGO_SZ).
        session             — Shared requests.Session for connection pooling.
        failed_set          — Set of URLs that permanently failed (session-scoped).
        executor            — ThreadPoolExecutor to run the background task.
        logo_ready_signal   — pyqtSignal(object, object) to emit (widget_ref, QPixmap).
        card_ref            — Widget (or any QObject) to pass back as the first argument.
        default_pixmap      — Fallback pixmap if loading fails.
        mem_cache           — In-memory {key: QPixmap} dict.
        mem_keys            — Ordered list of cache keys for LRU eviction.
        mem_lock            — Lock protecting mem_cache / mem_keys.
        max_mem_entries     — Max items before LRU eviction fires.
    """
    import requests  # late import to avoid module-level dep

    key = f"{url}@{size}"

    with mem_lock:
        if key in mem_cache:
            logo_ready_signal.emit(card_ref, mem_cache[key])
            return

    def task():
        if url in failed_set:
            logo_ready_signal.emit(card_ref, default_pixmap)
            return
        try:
            raw_bytes = db_logo_get(url, size)
            from_db = raw_bytes is not None
            if not from_db:
                r = session.get(url, timeout=LOGO_TIMEOUT, verify=True, stream=True)
                try:
                    r.raise_for_status()
                    raw_bytes = r.raw.read(LOGO_MAX_BYTES, decode_content=True)
                finally:
                    r.close()
            processed = process_logo_bytes(raw_bytes, size)
            if processed is None:
                failed_set.add(url)
                logo_ready_signal.emit(card_ref, default_pixmap)
                return
            if not from_db:
                buf = io.BytesIO()
                processed.save(buf, format="PNG")
                db_logo_put(url, size, buf.getvalue())
            pixmap = _pil_to_qpixmap(processed)
            with mem_lock:
                mem_cache[key] = pixmap
                mem_keys.append(key)
                purge_mem_logo_cache(mem_cache, mem_keys, max_mem_entries)
            logo_ready_signal.emit(card_ref, pixmap)
        except Exception as e:
            log(f"Logo load failed ({url!r}): {e}", "debug")
            failed_set.add(url)
            logo_ready_signal.emit(card_ref, default_pixmap)

    executor.submit(task)