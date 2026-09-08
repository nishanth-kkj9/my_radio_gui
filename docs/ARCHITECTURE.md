# Architecture

Smart Radio Pro is a single-process desktop application organized as a small layered Python package. The design keeps network access, playback, UI, persistence, and caching in separate modules while using Qt signals, timers, and worker threads to keep the interface responsive.

## System overview

```text
┌─────────────────────────────────────────────────────────────┐
│                         Qt Application                     │
│                       src/.../main.py                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         ui/app_ui.py                       │
│  Main window • search • station grid • dialogs • shortcuts │
└──────┬───────────────────┬──────────────────┬──────────────┘
       │                   │                  │
       ▼                   ▼                  ▼
┌───────────────┐  ┌────────────────┐  ┌────────────────────┐
│ services/     │  │ core/player.py │  │ utils/              │
│ station_      │  │ libVLC wrapper  │  │ storage/stats/logo │
│ service.py    │  │ health/retry    │  │ cache/logger/etc.  │
└──────┬────────┘  └────────────────┘  └────────────────────┘
       │
       ▼
┌──────────────────────┐
│      core/api.py     │
│ Radio Browser client │
│ mirrors/retries/URL  │
└──────────┬───────────┘
           │
           ▼
     Radio Browser API
```

## Module responsibilities

### `core/`

- **`api.py`** — HTTP client for Radio Browser, mirror failover, request retries, URL validation, and favicon sanitization.
- **`config.py`** — central configuration constants: timeouts, cache limits, UI sizes, categories, timing, reconnect policy, and feature flags.
- **`equalizer.py`** — model for the 10-band EQ, presets, gain validation, and change callbacks.
- **`player.py`** — thread-safe libVLC integration, playback state, volume/mute, fade effects, metadata, health checks, reconnect logic, and EQ application.
- **`state.py`** — small state container for station/volume/mute values; it is not the primary session persistence layer.
- **`theme.py`** — centralized palette used by the Qt widgets.

### `services/`

- **`station_service.py`** — translates categories to Radio Browser queries, deduplicates station URLs, maintains the in-memory TTL cache, and preloads popular categories on a background executor.

### `ui/`

- **`app_ui.py`** — application controller and main window. It owns most user interactions, dialogs, timers, async callbacks, favorites/recent handling, rendering, and session restoration.
- **`components.py`** — reusable station card widget and presentation helpers.
- **`mini_player.py`** — compact always-on-top playback window.
- **`spectrum.py`** — custom QPainter-based animated spectrum widget.

### `utils/`

- **`storage.py`** — atomic JSON persistence for favorites, recent stations, and session state.
- **`stats.py`** — atomic JSON playback statistics with thread protection.
- **`logo_cache.py`** — SQLite-backed persistent image cache.
- **`logo_loader.py`** — shared logo download/processing pipeline combining memory cache, SQLite, and network loading.
- **`maintenance.py`** — startup integrity checks and in-memory cache eviction.
- **`logger.py`** — rotating application log.
- **`notifier.py`** — cross-platform notification helper; currently not wired into the main playback flow.

## Startup sequence

1. `main.py` installs a process-level exception hook.
2. `QApplication` is configured with Fusion style and a global font.
3. `RadioUI` loads session JSON and restores window/session settings.
4. `RadioPlayer` initializes libVLC and starts a background health thread.
5. The UI creates its timers, signals, worker executor, caches, and default logos.
6. The selected category is fetched asynchronously.
7. Popular categories are preloaded in the background.
8. SQLite logo-cache maintenance runs in the background.
9. If auto-resume is enabled and a last station exists, playback is resumed after the configured delay.

## Station discovery flow

```text
Category selection
      │
      ▼
RadioUI._fetch()
      │
      ▼
station_service.fetch_category()
      │
      ├── cache hit ─────────────► return cached stations
      │
      └── cache miss
             │
             ▼
        _fetch_fresh()
             │
             ├── name queries or tag queries
             ▼
          core/api.py
             │
             ├── mirror 1
             ├── mirror 2
             └── mirror 3
             │
             ▼
      station validation/parsing
             │
             ▼
       URL deduplication
             │
             ▼
     TTL cache + Qt signal
```

Concurrent requests for the same category are coordinated by a condition variable so duplicate callers wait for the in-flight fetch rather than issuing parallel duplicate API requests.

## Playback flow

```text
User selects station
        │
        ▼
RadioUI._play()
        │
        ▼
core/player.py::play()
        │
        ├── validate stream URL
        ├── stop previous media
        ├── create libVLC media
        ├── apply network/live caching options
        └── start playback
        │
        ▼
VLC events + health loop
        │
        ├── Playing
        ├── Buffering
        ├── Error / Ended
        └── reconnect attempts
```

Reconnect attempts are serialized with a lock. The player uses a bounded delay sequence and stops permanently after the configured maximum, notifying the UI through the injected failure callback.

## Threading model

The application uses several kinds of background work:

| Worker | Purpose | UI interaction |
|---|---|---|
| `ThreadPoolExecutor` in `RadioUI` | Station fetches and logo work | Qt signals |
| Preload executor | Category preloading | Logging/cache only |
| `vlc-health` daemon thread | Playback health monitoring | Player state only |
| `recover` daemon thread | Reconnect after VLC failures | Player state |
| Fade threads | Non-blocking volume ramps | VLC audio API |
| `threading.Timer` | Sleep timer | `invoke_main()` |
| Qt main thread | Widgets, dialogs, timers, painting | Direct |

The `_Invoker` signal in `app_ui.py` provides a safe path back to the Qt main thread for callbacks originating from non-Qt threads.

## Caching layers

There are three practical cache layers:

1. **Station cache** — in-memory, category-based, with a configurable TTL.
2. **Logo memory cache** — in-memory `QPixmap` objects with bounded size.
3. **Logo SQLite cache** — persistent PNG bytes keyed by URL and size.

The logo pipeline checks memory first, then SQLite, then the network. Permanent logo failures are recorded for the current process so repeated rendering does not repeatedly request a known-bad URL.

## Persistence model

The application uses atomic JSON writes (`write temp file` → `os.replace`) for user state.

```text
favorites.json ─┐
recent.json     ├──► local user state
session.json    │
stats.json      ┘

logos.db ─────────► persistent logo cache
radio_log.txt ────► rotating diagnostics log
```

These artifacts are runtime state, not source files, and should remain outside version control.

## UI composition

The main window is composed of:

- Header: branding, search, add-station, help, mini-player toggle, mute, volume.
- Category bar: 10 built-in categories.
- Scrollable content: loading state, empty state, sortable station grid, favorites/recent.
- Now-playing bar: artwork, spectrum, metadata, live/buffering state, EQ, sleep timer.

The application also uses modal dialogs for:

- Equalizer
- Sleep timer
- Add custom station
- Station information
- Help/shortcuts and data export/import actions

## Extension points

Common places to extend the application:

- Add or change categories/query behavior → `core/config.py`, `services/station_service.py`
- Change player/reconnect behavior → `core/player.py`
- Add EQ presets → `core/equalizer.py`
- Add persistent user fields → `utils/storage.py` and `RadioUI.closeEvent()`
- Add station-card behavior → `ui/components.py`
- Add main-window functionality → `ui/app_ui.py`
- Add a reusable visual component → `ui/`
- Add another runtime cache → follow the separation used by `logo_cache.py`
- Add automated tests → `tests/`

Keep network access, long-running work, and blocking operations outside the Qt GUI thread.

## Shutdown sequence

On close, the UI:

1. Stops timers and transient overlays.
2. Finalizes the current listening-time statistic.
3. Stops and releases the VLC player.
4. Shuts down the logo/executor worker pool without waiting for running tasks.
5. Saves current session settings, geometry, EQ state, search history, and last station.

Callbacks that arrive after shutdown are guarded by the UI's `_closing` state.
