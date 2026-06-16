# Smart Radio Pro

A modern internet radio player built with PyQt6 and VLC.

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4+-green)](https://www.riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Version](https://img.shields.io/badge/version-13.1-blue)]()

## Features

- **15 Built-in Stations Categories** — Top Charts, Hindi, Kannada, Pop, Rock, Jazz, Classical, News, Recent, Favorites
- **Auto-Resume** — Remembers and resumes your last playing station on launch
- **Mouse-Wheel Volume** — Scroll anywhere on the header or now-playing bar to adjust volume
- **Mini-Player Mode** — Compact always-on-top player (Ctrl+M toggle)
- **Volume Fade** — Smooth fade-in on play, fade-out on stop
- **Playback Statistics** — Track listening time and most-played stations
- **Search with History** — Search stations with searchable dropdown history
- **Equalizer** — 5-band audio equalizer with presets
- **Sleep Timer** — Auto-stop playback after set duration
- **Desktop Notifications** — OS notifications when track changes
- **M3U Export** — Export favorites as playlist files
- **Window Geometry** — Remembers size and position between sessions

## Requirements

### Software
- **VLC Media Player** (64-bit) — [Download](https://www.videolan.org/vlc/)
- **Python 3.10+**

### Python Packages
```
pip install -r requirements.txt
```

## Quick Start

```bash
# Clone the repository
cd smart_radio_pro_PyQt6_v13

# Create virtual environment (recommended)
python -m venv venv
source venv/Scripts/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r smart_radio_v13/requirements.txt

# Run the app
python smart_radio_v13/main.py
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
smart_radio_pro_PyQt6_v13/
├── LICENSE              # MIT License
├── README.md           # This file
├── .gitignore         # Git ignore patterns
├── smart_radio_v13/
│   ├── __init__.py
│   ├── main.py        # Entry point
│   ├── requirements.txt
│   ├── CHANGELOG.md  # Version history
│   ├── core/        # Player, config, theme, state, equalizer
│   ├── services/    # Station fetching with caching
│   ├── ui/          # Main UI, mini-player, components
│   ├── utils/       # Logo cache, storage, logger, stats
│   └── tests/       # Test modules
```

## Configuration

All settings are in `core/config.py`:
- Station categories and search queries
- UI layout (card size, columns)
- Timing (timers, debounce intervals)
- Cache settings (TTL, max entries)
- Volume and fade settings

## Known Issues

- **VLC not found** — Ensure VLC (64-bit) is installed and matches your Python architecture
- **No audio** — Check system volume and mute status

## License

MIT License

## Credits

- [Radio Browser API](https://www.radio-browser.info/) — Station data
- [VideoLAN](https://www.videolan.org/) — VLC engine
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — UI framework