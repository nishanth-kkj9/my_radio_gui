"""
core/api.py — Radio Browser API client (multi-mirror, retry, favicon sanitisation).

FIX: _get_session() now uses a threading.Lock so two threads can never
     simultaneously create duplicate Sessions (double-checked locking pattern).
"""

from __future__ import annotations

import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse

from core.config import API_TIMEOUT, ALLOWED_STREAM_SCHEMES
from utils.logger import log

API_HOSTS = [
    "https://de1.api.radio-browser.info",
    "https://fr1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]

USER_AGENT  = "SmartRadioPro/3.0 (python-vlc)"
_BAD_FAVICON = {"", "null", "none", "undefined", "false", "0"}

_session:      requests.Session | None = None
_session_lock: threading.Lock          = threading.Lock()   # FIX

_logo_session:      requests.Session | None = None
_logo_session_lock: threading.Lock          = threading.Lock()


def _get_session() -> requests.Session:
    global _session
    if _session is not None:          # fast path, no lock needed
        return _session
    with _session_lock:               # FIX: only one thread initialises
        if _session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            retry = Retry(
                total=3, backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retry)
            s.mount("http://",  adapter)
            s.mount("https://", adapter)
            _session = s
    return _session


def get_logo_session() -> requests.Session:
    """
    Return a shared requests.Session for logo (favicon) downloads.

    Kept separate from the API session so:
      • 403 / 404 logo failures don't pollute the API retry budget.
      • No retry adapter — permanent failures (403, DNS NXDOMAIN) are cached
        immediately in _failed_logo_cache; retrying would only add latency.
      • Connection pooling is still shared across all logo download threads.
    """
    global _logo_session
    if _logo_session is not None:
        return _logo_session
    with _logo_session_lock:
        if _logo_session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            # Minimal adapter — single attempt, no retry.
            s.mount("http://",  HTTPAdapter(max_retries=0))
            s.mount("https://", HTTPAdapter(max_retries=0))
            _logo_session = s
    return _logo_session


def is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ALLOWED_STREAM_SCHEMES and bool(p.netloc)
    except Exception:
        return False


def _clean_favicon(raw: str) -> str:
    if not raw:
        return ""
    url = raw.strip()
    if url.lower() in _BAD_FAVICON:
        return ""
    for prefix in ("https://", "http://"):
        last = url.rfind(prefix, 1)
        if last > 0:
            url = url[last:]
            break
    try:
        p = urlparse(url)
        if p.scheme in ("http", "https") and p.netloc:
            return url
    except Exception:
        pass
    return ""


def _get(path: str, params: dict, timeout: int = API_TIMEOUT) -> list:
    last_err = None
    for host in API_HOSTS:
        try:
            r = _get_session().get(
                f"{host}{path}", params=params,
                timeout=(4, timeout), verify=True,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            last_err = e
    log(f"API failed on all mirrors: {last_err}", "error")
    return []


def _parse_station(s: dict) -> dict | None:
    url = s.get("url_resolved") or s.get("url", "")
    if not url or not is_safe_url(url):
        return None
    return {
        "name":    s.get("name", "Unknown").strip(),
        "url":     url,
        "logo":    _clean_favicon(s.get("favicon", "")),
        "country": s.get("country", "").strip(),
        "tags":    s.get("tags",    "").strip(),
        "bitrate": s.get("bitrate", 0),
        "votes":   s.get("votes",   0),
        "codec":   s.get("codec",   "").strip(),
        "language": s.get("language", "").strip(),
        "stationuuid": s.get("stationuuid", ""),
    }


def fetch_stations(query: str, limit: int = 30) -> list[dict]:
    try:
        data = _get("/json/stations/search", {
            "name": query, "limit": limit,
            "hidebroken": "true", "order": "clickcount", "reverse": "true",
        })
        return [p for s in data if (p := _parse_station(s))]
    except Exception as e:
        log(f"fetch_stations error for '{query}': {e}", "error")
        return []


def fetch_stations_by_tag(tag: str, limit: int = 30) -> list[dict]:
    try:
        data = _get(f"/json/stations/bytag/{tag}", {
            "limit": limit, "hidebroken": "true",
            "order": "clickcount", "reverse": "true",
        })
        return [p for s in data if (p := _parse_station(s))]
    except Exception as e:
        log(f"fetch_stations_by_tag error '{tag}': {e}", "error")
        return []
