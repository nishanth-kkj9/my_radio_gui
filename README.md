# Smart Radio Pro

[![CI](https://github.com/nishanth-kkj9/my_radio_gui/actions/workflows/ci.yml/badge.svg)](https://github.com/nishanth-kkj9/my_radio_gui/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-41CD52.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Version](https://img.shields.io/badge/version-13.1-0ea5e9.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A desktop internet-radio player built with **PyQt6**, **libVLC**, and the **Radio Browser API**.

Smart Radio Pro combines station discovery, resilient streaming playback, local favorites/history, cached station logos, an animated spectrum display, a 10-band equalizer, a compact mini-player, and persistent session state in a single desktop application.

## Highlights

- **Station discovery** across 10 built-in categories, including Top Charts, Hindi, Kannada, Pop, Rock, Jazz, Classical, News, Recent, and Favorites.
- **Search and sorting** over station name, country, tags, and language, with recent-search history.
- **Resilient playback** with URL validation, VLC health monitoring, multi-mirror API access, reconnect attempts, and volume fade effects.
- **10-band equalizer** with presets and manual gain control from -20 dB to +20 dB.
- **Persistent local state** for favorites, recently played stations, window geometry, EQ settings, search history, and the last station.
- **Logo caching** using an in-memory cache plus a persistent SQLite cache.
- **Mini-player mode** with always-on-top behavior, drag repositioning, mute, next-station navigation, and volume control.
- **Playback statistics** with play counts, all-time listening time, and a Most Played sort mode.
- **Sleep timer**, station information, context actions, random playback, and keyboard-first controls.
- **Playlist interoperability** through JSON favorites import/export and M3U export.

## Requirements

### Runtime

- Python **3.10 or newer**
- VLC Media Player (64-bit recommended on Windows)
- Internet access for Radio Browser station discovery and remote station streams

Python dependencies are declared in `pyproject.toml`:

- PyQt6
- python-vlc
- requests
- Pillow
- urllib3

### Platform notes

Windows is the primary desktop target. The player contains Windows-specific VLC DLL discovery, while the notification helper includes platform-specific implementations for Windows, macOS, and Linux. Continuous integration currently validates a Linux headless environment and does not represent full desktop QA on every platform.

## Installation

### 1. Install VLC

Install VLC Media Player from [VideoLAN](https://www.videolan.org/vlc/) before starting the application.

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

### 3. Install the project

For normal use:

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

The repository keeps `requirements.txt` as a simple runtime dependency list, but `pyproject.toml` is the authoritative packaging configuration.

## Run

Recommended:

```bash
smart-radio-pro
```

Direct source execution is also supported:

```bash
python src/smart_radio_pro/main.py
```

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Space` | Stop playback or resume the most recent station |
| `M` | Mute / unmute |
| `F` | Add/remove the current station from Favorites |
| `R` | Refresh the current category |
| `N` | Play a random station |
| `←` / `→` | Previous / next station |
| `↑` / `↓` | Increase / decrease volume by 5% |
| `Ctrl+F` | Focus the search field |
| `Ctrl+M` | Toggle mini-player mode |
| `Ctrl+U` | Add a custom station |
| `T` | Toggle always-on-top |
| `Escape` | Cancel auto-resume / clear search |
| `?` | Open help and shortcuts |

Mouse-wheel volume control is available over the header and now-playing bar.

## Application layout

```text
my_radio_gui/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── config.yml
│   │   └── feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── ci.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CONFIGURATION.md
│   ├── DEVELOPMENT.md
│   ├── README.md
│   └── TROUBLESHOOTING.md
├── src/
│   └── smart_radio_pro/
│       ├── core/
│       │   ├── api.py
│       │   ├── config.py
│       │   ├── equalizer.py
│       │   ├── player.py
│       │   ├── state.py
│       │   └── theme.py
│       ├── services/
│       │   └── station_service.py
│       ├── ui/
│       │   ├── app_ui.py
│       │   ├── components.py
│       │   ├── mini_player.py
│       │   └── spectrum.py
│       ├── utils/
│       │   ├── logger.py
│       │   ├── logo_cache.py
│       │   ├── logo_loader.py
│       │   ├── maintenance.py
│       │   ├── notifier.py
│       │   ├── stats.py
│       │   └── storage.py
│       ├── __init__.py
│       └── main.py
├── tests/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── LICENSE
├── README.md
├── SECURITY.md
├── SUPPORT.md
├── pyproject.toml
└── requirements.txt
```

Detailed module responsibilities and runtime data flow are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Runtime data

The application writes user and cache data locally. These files are intentionally not part of source control:

| File | Purpose |
|---|---|
| `src/smart_radio_pro/favorites.json` | Saved favorite stations |
| `src/smart_radio_pro/recent.json` | Recently played stations |
| `src/smart_radio_pro/session.json` | UI, playback, and session state |
| `src/smart_radio_pro/stats.json` | Playback statistics |
| `src/smart_radio_pro/logos.db` | Persistent SQLite logo cache |
| `src/smart_radio_pro/radio_log.txt` | Rotating application log |

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for cache limits and persistence details.

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run linting:

```bash
ruff check src/
```

Run the current CI-equivalent smoke checks locally:

```bash
python -c "from smart_radio_pro.core import config, theme, equalizer; print('Core modules OK')"
python -c "from smart_radio_pro.core.player import RadioPlayer; print('Player OK')"
```

The current repository contains the `pytest` development dependency, but the tracked `tests/` package does not yet contain functional test cases. CI therefore focuses on linting and import smoke tests at present. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Data flow at a glance

```text
Radio Browser API
       │
       ▼
core/api.py ──► services/station_service.py ──► Qt UI
       │                    │
       │                    └── in-memory TTL cache
       │
       └── URL validation / retries / mirrors

Qt UI ──► core/player.py ──► libVLC ──► Internet radio stream
  │               │
  │               ├── health monitor
  │               ├── reconnect logic
  │               └── equalizer
  │
  ├── utils/storage.py ──► local JSON state
  ├── utils/stats.py ────► listening statistics
  └── utils/logo_loader.py ─► memory cache + SQLite logo cache
```

## Known limitations

- Stream quality and reliability ultimately depend on third-party radio stations and network conditions.
- Radio Browser metadata is external data and can be incomplete or inconsistent.
- VLC must be installed separately; Python bindings alone are not sufficient.
- The current CI pipeline is a smoke/quality gate, not a full end-to-end GUI test suite.
- `utils/notifier.py` contains cross-platform notification support, but the current main UI no longer wires notification preferences or ICY-change notifications into the playback flow.
- Custom-station input is validated through the application's stream-scheme allowlist; the current dialog specifically describes HTTP/HTTPS entry.

## Credits

- [Radio Browser](https://www.radio-browser.info/) — station directory and metadata
- [VideoLAN](https://www.videolan.org/) — libVLC playback engine
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — desktop UI toolkit

## License

Smart Radio Pro is distributed under the [MIT License](LICENSE).
