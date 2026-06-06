# core/config.py — All tuneable constants in one place.  (v6)

# ── Network ────────────────────────────────────────────────────────────────────
API_TIMEOUT    = 8        # seconds per API host attempt
LOGO_TIMEOUT   = 6        # seconds for logo download
LOGO_MAX_BYTES = 512_000  # 500 KB cap per favicon

# ── Allowed stream URL schemes ─────────────────────────────────────────────────
ALLOWED_STREAM_SCHEMES = {"http", "https", "rtsp", "rtp", "mms", "rtmp"}

# ── VLC instance flags ─────────────────────────────────────────────────────────
VLC_INSTANCE_ARGS = [
    "--no-video",
    "--quiet",
    "--network-caching=3000",
    "--live-caching=3000",
    "--http-reconnect",
    "--sout-mux-caching=3000",
]

# ── Health / reconnect ─────────────────────────────────────────────────────────
HEALTH_INTERVAL  = 8
MAX_RECONNECT    = 5
RECONNECT_DELAYS = [2, 4, 8, 16, 30]

# ── SQLite logo cache (disk) ───────────────────────────────────────────────────
LOGO_DB_MAX_ENTRIES = 2000    # max logos stored in SQLite
LOGO_DB_TTL_DAYS    = 30      # evict logos older than this many days

# ── In-memory cache ────────────────────────────────────────────────────────────
MEM_CACHE_MAX = 200   # max PhotoImage objects kept in memory
CACHE_TTL     = 600   # station data TTL in seconds (10 min)

# ── UI layout ──────────────────────────────────────────────────────────────────
COLS        = 5   # 192px cards × 5 + padding ≈ 1000px+ window width
MAX_RESULTS = 30
LOGO_SZ     = 96    # card logo px
THUMB_SZ    = 48    # now-bar thumbnail px
MINI_LOGO_SZ = 44   # mini-player logo px

# ── Timing ─────────────────────────────────────────────────────────────────────
DEBOUNCE_MS  = 250
SPINNER_MS   = 180
EQ_MS        = 75
TIMER_MS     = 1000
ICY_POLL_MS  = 4000

# ── Workers ────────────────────────────────────────────────────────────────────
MAX_WORKERS = 8

# ── Categories ─────────────────────────────────────────────────────────────────
CATEGORIES = [
    ("Top Charts", "top"),
    ("Hindi",      "hindi"),
    ("Kannada",    "kannada"),
    ("Pop",        "pop"),
    ("Rock",       "rock"),
    ("Jazz",       "jazz"),
    ("Classical",  "classical"),
    ("News",       "news"),
    ("Recent",     "recent"),
    ("Favorites",  "favorites"),
]

QUERY_MAP = {
    "top":       ["top hits", "india"],
    "hindi":     ["hindi", "bollywood"],
    "kannada":   ["kannada", "karnataka"],
    "pop":       ["pop", "pop hits"],
    "rock":      ["rock", "classic rock"],
    "jazz":      ["jazz", "smooth jazz"],
    "classical": ["classical", "orchestra"],
    "news":      ["news", "bbc news"],
}

PRELOAD_CATEGORIES = ["hindi", "kannada", "pop", "rock", "jazz", "classical", "news"]

MAX_RECENT = 20

# ── Volume step for keyboard shortcuts ────────────────────────────────────────
VOLUME_STEP = 5   # % per keypress

# ─────────────────────────────────────────────────────────────────────────────
# v6 — New feature constants
# ─────────────────────────────────────────────────────────────────────────────

# Auto-resume last playing station on launch
AUTO_RESUME       = True
AUTO_RESUME_DELAY = 1800    # ms to wait before auto-resuming (lets UI settle)

# Smooth volume fade-in / fade-out
FADE_IN_STEPS     = 22
FADE_OUT_STEPS    = 18
FADE_IN_INTERVAL  = 0.040   # seconds between fade-in steps
FADE_OUT_INTERVAL = 0.035   # seconds between fade-out steps

# Search history
SEARCH_HISTORY_MAX = 12

# OS desktop notifications
NOTIFY_ON_ICY_CHANGE = True   # notify when ICY track title changes

# Playback statistics
STATS_ENABLED = True

# Sort options (label, dict-key-or-None, reverse)
# "_plays" is a virtual key injected at render time from stats
SORT_OPTIONS = [
    ("Default",     None,      False),
    ("Name A–Z",    "name",    False),
    ("Bitrate ↑",   "bitrate", True),
    ("Votes ↑",     "votes",   True),
    ("Country",     "country", False),
    ("Most Played", "_plays",  True),
]
