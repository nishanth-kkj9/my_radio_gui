# Changelog — Smart Radio Pro

## v13.1 (UI & Stability Improvements)

### Critical Bug Fixes
- **FIXED: `_make_default_logo()` crash** — Function referenced `Image`, `ImageDraw`,
  and `_pil_to_qpixmap` which were never imported in `app_ui.py`, causing a
  `NameError` on every launch. Replaced with a pure QPainter implementation that
  requires no PIL dependency.
- **FIXED: Global exception handler** — Added `sys.excepthook` override in
  `main.py` that catches and logs uncaught exceptions instead of silently crashing.

### UI Improvements
- **Keyboard shortcut hint visibility** — The bottom hint bar now uses the theme's
  `TEXT_DIM` color instead of a hardcoded near-invisible `#25304a`.
- **Global font configuration** — Sets "Segoe UI" 9pt with antialiasing at app
  startup for consistent cross-platform rendering.
- **Window title updated** to "Smart Radio Pro v13.1".

### Stability Improvements
- **Mini player position caching** — `_mini_pos_cache` is read from session once
  at startup and kept in memory. Opening the mini player no longer performs disk
  I/O via `load_session()`. Position is updated in-memory when the mini player is
  destroyed and persisted to disk on close.
- **Type annotations** — `QBrush` import added (replaces unused `QPen`), type
  annotations for exception hook parameters.