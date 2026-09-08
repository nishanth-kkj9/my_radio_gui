# Configuration

Runtime tuning is intentionally centralized in [`src/smart_radio_pro/core/config.py`](../src/smart_radio_pro/core/config.py). The application does not currently expose a separate environment-variable or config-file override layer.

## Network and station access

| Constant | Current value | Purpose |
|---|---:|---|
| `API_TIMEOUT` | `8` s | Per Radio Browser host request timeout |
| `LOGO_TIMEOUT` | `6` s | Logo download timeout |
| `LOGO_MAX_BYTES` | `512000` | Maximum logo response bytes read |
| `ALLOWED_STREAM_SCHEMES` | HTTP/HTTPS/RTSP/RTP/MMS/RTMP | Stream URL allowlist |

The Radio Browser client uses three HTTPS API mirrors and retries selected transient HTTP status codes.

## Playback and reconnect

| Constant | Current value | Purpose |
|---|---:|---|
| `HEALTH_INTERVAL` | `8` s | Player health polling interval |
| `MAX_RECONNECT` | `5` | Maximum reconnect attempts |
| `RECONNECT_DELAYS` | `2, 4, 8, 16, 30` s | Backoff sequence |
| `VLC_INSTANCE_ARGS` | VLC options | Headless/network playback behavior |

On Windows, `core/player.py` searches common VLC installation paths, registry entries, and the system `PATH` to locate `libvlc.dll`.

## Station cache

| Constant | Current value | Purpose |
|---|---:|---|
| `CACHE_TTL` | `600` s | Station category TTL |
| `MAX_RESULTS` | `30` | Maximum displayed stations |
| `PRELOAD_CATEGORIES` | 7 categories | Background category warm-up |

Category definitions and Radio Browser search terms are in `CATEGORIES` and `QUERY_MAP`.

## Logo cache

| Constant | Current value | Purpose |
|---|---:|---|
| `LOGO_DB_MAX_ENTRIES` | `2000` | Maximum persistent logo entries |
| `LOGO_DB_TTL_DAYS` | `30` days | Persistent logo expiration |
| `MEM_CACHE_MAX` | `200` | Maximum in-memory logo objects |

Persistent logos are stored in `src/smart_radio_pro/logos.db`.

## UI and timing

Important UI values include:

- `COLS = 5` — station-grid columns
- `LOGO_SZ = 96`
- `THUMB_SZ = 48`
- `MINI_LOGO_SZ = 44`
- `DEBOUNCE_MS = 250`
- `SPINNER_MS = 180`
- `EQ_MS = 75`
- `TIMER_MS = 1000`
- `ICY_POLL_MS = 4000`
- `MAX_WORKERS = 8`

The station-card itself is 192×268 pixels.

## Feature settings

| Constant | Current value | Purpose |
|---|---:|---|
| `AUTO_RESUME` | `True` | Resume the last station on launch |
| `AUTO_RESUME_DELAY` | `1800` ms | Delay before auto-resume |
| `SEARCH_HISTORY_MAX` | `12` | Persisted search history |
| `STATS_ENABLED` | `True` | Playback statistics |
| `VOLUME_STEP` | `5` | Keyboard/wheel volume step |

## Equalizer

The equalizer is a **10-band** model:

```text
60Hz  170Hz  310Hz  600Hz  1kHz
3kHz  6kHz   12kHz  14kHz  16kHz
```

Gain is clamped between **-20 dB and +20 dB**.

Presets currently include:

- None
- Flat
- Bass Boost
- Bass Cut
- Treble Boost
- Treble Cut
- Rock
- Pop
- Jazz
- Classical
- Dance
- Vocal Boost
- Lounge
- Custom

## Persistence

User/session files are managed by `utils/storage.py`:

- `favorites.json`
- `recent.json`
- `session.json`

Playback statistics are stored by `utils/stats.py`:

- `stats.json`

The session object currently includes volume, category, EQ state, sorting mode, window geometry, always-on-top state, last station, search history, and mini-player position.

## Safe customization rules

When changing a constant:

1. Keep the value in `core/config.py` rather than duplicating it in UI code.
2. Update the relevant documentation when behavior changes.
3. Check the CI smoke tests after changes.
4. For user-visible changes, update `CHANGELOG.md`.

Avoid adding secrets, API keys, or personal tokens to the repository. The current project does not require an application secret for normal Radio Browser usage.

## Source of truth

Use this precedence when describing behavior:

1. Executable code in `src/`
2. `pyproject.toml` for packaging/development dependencies
3. CI workflow for what automation actually validates
4. README and `docs/` for user-facing explanation

Documentation should be updated when those sources change.
