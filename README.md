# Smart Radio Pro

A modern internet radio player built with PyQt6 and VLC.

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4+-green)](https://www.riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-13.1-blue)](CHANGELOG.md)

## Features

- **15 Built-in Station Categories** — Top Charts, Hindi, Kannada, Pop, Rock, Jazz, Classical, News, Recent, Favorites
- **Auto-Resume** — Remembers and resumes your last playing station on launch
- **Mouse-Wheel Volume** — Scroll anywhere on the header or now-playing bar to adjust volume
- **Mini-Player Mode** — Compact always-on-top player (`Ctrl+M`)
- **Volume Fade** — Smooth fade-in on play, fade-out on stop
- **Playback Statistics** — Track listening time and most-played stations
- **Search with History** — Searchable dropdown of past queries
- **Equalizer** — 5-band audio equalizer with presets
- **Sleep Timer** — Auto-stop playback after a set duration
- **Desktop Notifications** — OS notifications on track change
- **M3U Export** — Export favorites as a playlist file
- **Window Geometry** — Remembers size and position between sessions

## Requirements

- **VLC Media Player** (64-bit) — [Download](https://www.videolan.org/vlc/)
- **Python 3.10+**

## Installation

```bash
git clone https://github.com/nishanth-kkj9/my_radio_gui.git
cd my_radio_gui

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## Usage

```bash
python src/smart_radio_pro/main.py
```

Or install it as a package and use the console command:

```bash
pip install -e .
smart-radio-pro
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` | Volume up/down (5%) |
| `M` | Mute/unmute |
| `Space` | Play/pause |
| `←` / `→` | Previous/next station |
| `Ctrl+M` | Toggle mini-player |
| `Ctrl+F` | Focus search |
| `Ctrl+U` | Add custom station |
| `Ctrl+E` | Open equalizer |
| `T` | Toggle always-on-top |
| `Ctrl+S` | Export favorites |
| `Escape` | Cancel auto-resume / close dialogs |
| `?` | Show help |

## Project Structure

```
my_radio_gui/
├── .github/workflows/ci.yml   # CI: lint + import smoke test
├── src/
│   └── smart_radio_pro/
│       ├── main.py            # Entry point
│       ├── core/              # Player, config, theme, state, equalizer
│       ├── services/          # Station fetching with caching
│       ├── ui/                # Main window, mini-player, components
│       └── utils/             # Logo cache, storage, logger, stats
├── tests/                     # Test suite
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml             # Packaging metadata
├── README.md
└── requirements.txt
```

## Configuration

All tunable constants live in `src/smart_radio_pro/core/config.py`:
station categories and search queries, UI layout (card size, columns),
timing (timers, debounce intervals), cache settings (TTL, max entries),
and volume/fade behavior.

## Known Issues

- **VLC not found** — ensure VLC (64-bit) is installed and matches your Python architecture
- **No audio** — check system volume and mute status

## License

[MIT](LICENSE)

## Credits

- [Radio Browser API](https://www.radio-browser.info/) — station data
- [VideoLAN](https://www.videolan.org/) — VLC engine
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — UI framework
