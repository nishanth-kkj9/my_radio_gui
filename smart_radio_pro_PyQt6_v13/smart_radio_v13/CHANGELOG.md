# Smart Radio Pro — v6 Changelog

## New Features

### FEAT-1 · Auto-Resume Last Station
- On launch, automatically resumes the last playing station after 1.8 s
- Saved in `session.json` as `last_station`
- Press **Escape** within 1.8 s of launch to cancel

### FEAT-2 · Mouse-Wheel Volume Control
- Scroll the mouse wheel anywhere over the **header** or **now-playing bar** to adjust volume ±5%
- Works on Windows (delta), macOS, and Linux (Button-4/5)

### FEAT-3 · Always-on-Top Pin
- New **📌** button in the header pins/unpins the window above all others
- Keyboard shortcut: **T**
- State saved across sessions

### FEAT-4 · Mini Player Mode
- New **⧉** button collapses the app into a compact 370×80 px frameless overlay
- Keyboard shortcut: **Ctrl+M**
- Draggable anywhere on screen; stays always-on-top
- Shows: station logo · name · ICY track · stop · random · volume · expand button
- Click **⤢** (expand) to restore the full window

### FEAT-5 · Playback Statistics
- Every play is recorded to `stats.json` (play count + total listen time per station)
- Data persists across sessions

### FEAT-6 · "Most Played" Sort Option
- New sort button in the grid header: **Most Played**
- Stations are ranked by all-time play count from local stats

### FEAT-7 · Search History Dropdown
- Focuses the search box → shows a dropdown of your last 12 searches
- Click any term to instantly re-search
- Press **Enter** in the search box to commit and save the term

### FEAT-8 · OS Desktop Notifications
- When the ICY stream metadata changes (new song/track), a native OS notification fires
- Works on **Windows** (PowerShell balloon), **macOS** (osascript), **Linux** (notify-send)
- Debounced to max once per 20 s
- Toggle on/off in the **?** Help dialog — preference saved in session

### FEAT-9 · Window Geometry Save & Restore
- Window size and position are saved in `session.json` on close
- Restored exactly on next launch

### FEAT-10 · Volume Fade-In / Fade-Out
- Starting a station **fades in** from 0 → target volume over ~22 steps (0.9 s)
- Auto-resume on launch uses fade-in
- Stopping **fades out** before cutting audio

### FEAT-11 · M3U Playlist Export
- **? → Export M3U** saves your favorites as a standard `.m3u` playlist
- Compatible with VLC, foobar2000, Kodi, and any M3U-aware player
- Includes `#EXTINF` metadata (name, bitrate, country, tags, logo URL)

### FEAT-12 · Animated Slide-Up Toast
- Toast notifications now slide up smoothly from the bottom-right corner
- Replaces the static placement from v5

### FEAT-13 · Session Listening Time in Timer
- The now-playing timer now shows **session total** listen time alongside per-station time
  e.g. `On air  4:32    Session 23m`

### FEAT-14 · Per-Card Play-Count Badge
- Cards with play history show a small `▶N` badge (N = play count) in the top-right corner
- Provides at-a-glance "most listened" info without switching sort mode

### FEAT-15 · Notifications Toggle
- In the **?** Help dialog, a checkbox enables or disables OS desktop notifications
- Preference is saved in `session.json`

---

## Stability & Internal Improvements

| Area | Change |
|------|--------|
| `core/player.py` | Added `fade_in()` / `fade_out()` with threaded ramps |
| `core/config.py` | All new constants centralised; `SORT_OPTIONS` replaces scattered `_SORT_OPTIONS` |
| `utils/stats.py` | **New** — thread-safe play statistics with atomic JSON persistence |
| `utils/notifier.py` | **New** — cross-platform OS notifications, zero extra pip packages |
| `utils/storage.py` | Extended session schema (geometry, always-on-top, last station, search history, notifications) |
| `ui/mini_player.py` | **New** — frameless always-on-top compact player |
| `ui/app_ui.py` | +500 lines vs v5; all new features wired in; listen-time recorded on stop/switch/close |

## Files Added
- `utils/stats.py`
- `utils/notifier.py`
- `ui/mini_player.py`
- `CHANGELOG.md`

## Files Modified
- `main.py` — version bump
- `core/config.py` — new constants
- `core/player.py` — fade_in / fade_out methods
- `utils/storage.py` — extended session schema
- `ui/app_ui.py` — all v6 features

## v8 — Stability & Stylesheet Fixes

### Bugs Fixed

**1. DPI warning on Windows (`SetProcessDpiAwareness() failed: Access is denied`)**
- Root cause: Qt6 internally sets `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2` (the highest
  level) before any Python code runs. The old `main.py` then called
  `windll.shcore.SetProcessDpiAwareness(1)` which maps to `PROCESS_SYSTEM_DPI_AWARE` — a *lower*
  level — so Windows denied it and printed the warning.
- Fix: Removed the entire manual DPI awareness block from `main.py`. Qt6 handles High-DPI
  automatically; no explicit call is needed or desirable.

**2. "Could not parse stylesheet" — QSlider (volume, EQ panel, sleep dialog)**
Two separate QSS parser issues in every slider widget:
- **Missing whitespace between rule blocks**: Python string concatenation produced
  `...border-radius:2px;}QSlider::handle...` (no space between `}` and next selector).
  Qt6's QSS parser is stricter than Qt5 and rejects this. Fixed by adding a space: `}} `.
- **Negative margin shorthand rejected**: `margin:-4px 0` and `margin: 0 -3px` are not
  accepted by Qt6's QSS parser. Fixed by replacing with explicit directional properties:
  `margin-top: -4px; margin-bottom: -4px;` (horizontal sliders) and
  `margin-left: -3px; margin-right: -3px;` (vertical sliders).
- Affected: header volume slider, all 10 EQ band sliders, sleep dialog slider.

**3. "Could not parse stylesheet" — QPushButton (station cards)**
Same missing-whitespace issue in `StationCard`:
- `_play_btn_style()`: `...padding: 5px 10px; }QPushButton:hover { ... }` → added space.
- `fav_btn.setStyleSheet()`: `...padding: 3px 6px; }QPushButton:hover { ... }` → added space.
- Each stylesheet parse failure fired *twice* per widget (once on `setStyleSheet()`, once
  during subsequent repaint), causing hundreds of console lines during grid rendering.

**4. Buffering log flooding** (carried from v7)
- VLC fires `MediaPlayerBuffering` continuously during live stream playback even while audio
  is playing normally. Rate-limited to one log entry per 10 seconds.

### No UI changes
All 15 features from v7 are preserved unchanged. Only stability and log cleanliness improved.

## v9 — Bug Fixes + UI Refresh

### Bug Fixes

#### ❌ QPushButton "Could not parse stylesheet" (hundreds of warnings per session)
**Root cause:** Multi-rule QSS strings like `"QPushButton { ... } QPushButton:hover { ... }"`
set on buttons inside a `StationCard` (which has its own `setStyleSheet()`). Every time
`StationCard.setStyleSheet()` is called — which happens on every `enterEvent` and
`leaveEvent` — Qt6's cascade engine re-parses ALL child QPushButton stylesheets. The
parser fails silently but logs a warning for each button, each time.

**Fix:** All QPushButton widgets now use single-rule stylesheets (no `:hover` pseudo-state).
Hover state changes are handled explicitly via Python `enterEvent` / `leaveEvent` lambdas.
`WA_StyledBackground` is set on sub-frames to limit cascade propagation.

#### ❌ MiniPlayer volume QSlider malformed stylesheet
Missing whitespace between adjacent rule blocks + `margin: -3px 0` 2-value shorthand
(Qt6 rejects shorthand margin in QSS).  
**Fix:** Space added between blocks; `margin-top: -3px; margin-bottom: -3px;` used instead.

#### ❌ Header brand label showed "v7" instead of correct version
**Fix:** Updated to "v9".

#### ❌ Dead `_lbl` lambda in `_build_header`
Unused, broken lambda that shadowed nothing and was never called.  
**Fix:** Removed.

#### ❌ `_apply_border()` called redundantly at end of `_build()`
The card border was set once inline and once via `_apply_border()`, causing Qt6 to
re-evaluate all child QPushButton stylesheets twice at card creation time.  
**Fix:** Border is now set inline via `_set_card_style()` once at the end of `_build()`.

### UI Improvements
- Refined dark color palette: deeper backgrounds, better accent contrast, new `SURFACE3` / `BORDER2` levels
- Station cards: 192 × 268 px, better padding, cleaner button layout
- Tab bar: underline active-tab indicator (2px border-bottom on ACCENT)  
- Scrollbar: 4px width, accent-on-hover handle
- Context menu: rounded corners, better item padding and separators
- Dialogs: improved typography and borders
- Brand dot changed from ● to ◉ for visual depth
- Volume slider handle slightly larger (13px) for easier grabbing

## v11 — Mini Player Layout Fix + Full Stability Pass

### Bug Fixes

#### ❌ Mini player: expand (⤢) button and volume slider overlapping
**Root cause:** `CTRL_W = 148 px` was too narrow for the 4 controls inside it.
The pixel budget — `stop(~28) + random(~28) + vol_slider(80) + spacing(3×2) + expand(~22) ≈ 164 px` —
exceeded the reserved section width by ~16 px, so Qt squeezed the expand button
into the volume slider's space.  
**Fix (`ui/mini_player.py`):**
- `MINI_W` widened 440 → 475 px.
- `CTRL_W` widened 148 → 172 px (pixel budget now 157 px ≤ 172 px ✓).
- Volume slider narrowed 80 → 72 px to offset the wider CTRL_W.
- `ctrl_layout` spacing reduced 2 → 3 px (cleaner gaps).
- Expand button given an explicit `setFixedWidth(24)` — guaranteed space regardless of siblings.
- `ctrl_layout` alignment set to `AlignRight | AlignVCenter` so elements never drift left.

#### ❌ "Could not parse stylesheet" — QSlider (all sliders, every repaint)
**Root cause:** Qt 6 on Windows rejects **negative margins on the handle** sub-control
(`margin-top: -5px; margin-bottom: -5px;` and `margin-left: -3px; margin-right: -3px;`).
The parser logged the error **twice per slider per repaint** — producing dozens of
log lines every time the EQ panel or sleep timer dialog was opened.  
*Note: v8/v9 documented removing the margin shorthand (`margin: -4px 0`), but the
individual explicit negative properties also fail on Qt 6 Windows builds.*  
**Fix (all 3 slider sites in `ui/app_ui.py` + mini player slider):**
- Moved from negative handle margins to **positive groove margins** — same visual
  thin-track result, zero parse warnings:
  ```css
  /* Before (triggers warnings):                                           */
  QSlider::groove:horizontal { height: 4px; }
  QSlider::handle:horizontal { margin-top: -5px; margin-bottom: -5px; }

  /* After (Qt 6 safe):                                                    */
  QSlider::groove:horizontal { height: 4px; margin-top: 5px; margin-bottom: 5px; }
  QSlider::handle:horizontal { /* no margins needed */  }
  ```
- Applied to: header volume slider, mini player volume slider, all 10 EQ band sliders
  (vertical), sleep timer slider.

#### ❌ VLC not found on non-standard install paths
**Root cause:** `_ensure_vlc_path()` only checked 3 hardcoded paths, missing scoop /
winget / custom-prefix installs and non-C: drive installs.  
**Fix (`core/player.py`):**
- Added `%ProgramFiles%` and `%ProgramFiles(x86)%` env-var expansions as additional
  candidates (covers drives other than C:).
- Added **Windows Registry lookup** (HKLM + HKCU, both 32- and 64-bit hives under
  `SOFTWARE\VideoLAN\VLC`) — this is the canonical location where the VLC installer
  always writes `InstallDir`, regardless of prefix.
- De-duplicated all candidates before scanning (avoids redundant `os.path.isfile` calls).

#### ❌ Logo downloads using a bare `requests.get()` call
**Root cause:** `_load_logo()` in `app_ui.py` called `requests.get(url, ...)` directly,
creating a new TCP connection (and connection pool) for every logo, independent of the
shared API session.  
**Fix (`core/api.py` + `ui/app_ui.py`):**
- Added `get_logo_session()` — a lightweight shared `requests.Session` with connection
  pooling but **no retry adapter** (permanent logo failures are already handled by
  `_failed_logo_cache`; retrying 403/DNS would only add latency).
- `_load_logo()` now calls `get_logo_session().get(url, ...)`.
- Added an in-task double-check of `_failed_logo_cache` — if a URL was marked failed
  by a concurrent task between the time the task was queued and when it runs, the
  network call is skipped entirely.

#### ❌ Health monitor daemon thread could die silently on transient libvlc error
**Root cause:** `_health_loop()` had no exception guard around `get_state()`. A transient
libvlc internal error would propagate as an unhandled exception, killing the daemon thread
silently — with no reconnect protection for the remainder of the session.  
**Fix (`core/player.py`):** Wrapped the entire per-tick body in `try/except Exception`
with a `log(..., "warning")`. The thread continues looping; the next tick retries.

#### ❌ Queued logo tasks ran after window close (wasted work, potential crash)
**Root cause:** `executor.shutdown(wait=False)` did not cancel already-queued futures.
Logo tasks submitted just before close continued running (network requests, PIL decode)
for potentially seconds after the UI was destroyed.  
**Fix (`ui/app_ui.py`):** Uses `cancel_futures=True` on Python ≥ 3.9:
```python
try:
    self.executor.shutdown(wait=False, cancel_futures=True)
except TypeError:
    self.executor.shutdown(wait=False)   # Python < 3.9 fallback
```

### Summary of changed files
| File | Change |
|---|---|
| `ui/mini_player.py` | Layout fix (MINI_W/CTRL_W/slider/expand), QSS fix |
| `ui/app_ui.py` | QSS fix (3 sliders), logo session, cancel_futures shutdown |
| `core/api.py` | `get_logo_session()` — dedicated logo download session |
| `core/player.py` | VLC path detection (Registry + env vars), health loop guard |
| `CHANGELOG.md` | This entry |
