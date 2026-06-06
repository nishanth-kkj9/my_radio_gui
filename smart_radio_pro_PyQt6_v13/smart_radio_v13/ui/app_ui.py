"""
ui/app_ui.py — Smart Radio Pro v9  (PyQt6 port, bug-fixed + UI refresh)

All 15 v6 features are preserved:
  FEAT-1  Auto-resume last played station (1.8 s delay, cancellable)
  FEAT-2  Mouse-wheel volume control
  FEAT-3  Always-on-top toggle (keyboard: T)
  FEAT-4  Mini-player mode (Ctrl+M)
  FEAT-5  Playback statistics
  FEAT-6  "Most Played" sort option
  FEAT-7  Search history dropdown
  FEAT-8  OS desktop notifications on ICY track change
  FEAT-9  Window geometry saved & restored
  FEAT-10 Volume fade-in on play / fade-out on stop
  FEAT-11 M3U playlist export for favorites
  FEAT-12 Animated slide-up toast notifications
  FEAT-13 Total listening time shown in timer label
  FEAT-14 Per-card play-count badge
  FEAT-15 Notifications on/off toggle

Key Qt6 patterns used:
  • _Invoker signal — thread-safe "call on main thread" (replaces root.after(0,…))
  • QTimer.singleShot — replaces root.after(ms, callback)
  • QTimer instance — replaces after() IDs used for cancellation
  • pyqtSignal — typed signals for stations_loaded and logo_ready
  • QPainter — spectrum widget (see spectrum.py)
  • QScrollArea + QGridLayout — scrollable station grid
  • QDialog — all modal/floating panels
  • QMenu — right-click context menu
"""
from __future__ import annotations

import io
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageDraw
from PyQt6.QtCore import (
    Qt, QTimer, QObject, pyqtSignal, QPoint,
)
from PyQt6.QtGui import (
    QPixmap, QImage, QKeySequence, QShortcut,
    QWheelEvent, QColor, QPainter, QFont, QIcon,
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QLineEdit,
    QSlider, QScrollArea, QGridLayout, QVBoxLayout,
    QHBoxLayout, QFrame, QDialog,
    QApplication, QMenu, QCheckBox, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem,
)

from core.config import (
    COLS, DEBOUNCE_MS, EQ_MS, ICY_POLL_MS,
    LOGO_MAX_BYTES, LOGO_SZ, LOGO_TIMEOUT, MAX_RESULTS,
    MAX_WORKERS, MEM_CACHE_MAX, SPINNER_MS, THUMB_SZ, TIMER_MS,
    CATEGORIES, PRELOAD_CATEGORIES, MAX_RECONNECT, VOLUME_STEP,
    AUTO_RESUME, AUTO_RESUME_DELAY, MINI_LOGO_SZ,
    SORT_OPTIONS, SEARCH_HISTORY_MAX,
    STATS_ENABLED,
)
from core.equalizer import Equalizer
from core.player import RadioPlayer
from core.theme import (
    ACCENT, ACCENT2, BG, BORDER, BORDER2, GREEN, NOW_BAR,
    ORANGE, RED, SURFACE, SURFACE2, SURFACE3, TEXT, TEXT_DIM, TEXT_MID, YELLOW,
)
from services.station_service import fetch_category, preload_categories
from ui.components import _clean_name, StationCard
from ui.mini_player import MiniPlayer
from ui.spectrum import SpectrumWidget
from core.api import get_logo_session
from utils.logo_cache import (
    get as db_logo_get, put as db_logo_put,
    vacuum as db_vacuum, stats as db_stats,
)
from utils.logger import log
from utils.maintenance import purge_mem_logo_cache
import utils.stats as play_stats
from utils.storage import (
    load_favorites, save_favorites,
    load_recent, save_recent, add_to_recent,
    load_session, save_session,
)

_TOAST_MS       = 2800
_MARQUEE_MS     = 65
_TOAST_SLIDE_MS = 14
_TOAST_FRAMES   = 10


# ── Thread-safe "call on main thread" ─────────────────────────────────────────

class _Invoker(QObject):
    """
    Emit _signal from any thread; slot runs in the Qt main thread
    because auto-connection upgrades to QueuedConnection across threads.
    """
    _signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._signal.connect(self._run)

    def _run(self, func):
        func()

    def call(self, func):
        self._signal.emit(func)


_invoker = _Invoker()


def invoke_main(func):
    """Call *func* in the Qt main thread — safe to call from any thread."""
    _invoker.call(func)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ago(ts: float) -> str:
    if not ts:
        return ""
    diff = time.time() - ts
    if diff < 60:    return "just now"
    if diff < 3600:  return f"{int(diff // 60)} min ago"
    if diff < 86400: return f"{int(diff // 3600)}h ago"
    return f"{int(diff // 86400)}d ago"


def _fmt_time(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}:{s:02d}"


def _pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue())
    return pixmap


def _make_default_logo(size: int) -> QPixmap:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill="#1c2130")
    s = size
    draw.ellipse((int(s*.30), int(s*.52), int(s*.50), int(s*.68)), fill=ACCENT)
    draw.ellipse((int(s*.52), int(s*.50), int(s*.72), int(s*.66)), fill=ACCENT)
    draw.rectangle((int(s*.46), int(s*.18), int(s*.50), int(s*.58)), fill=ACCENT)
    draw.rectangle((int(s*.68), int(s*.16), int(s*.72), int(s*.56)), fill=ACCENT)
    draw.rectangle((int(s*.46), int(s*.18), int(s*.72), int(s*.24)), fill=ACCENT)
    return _pil_to_qpixmap(img)


# ── Toast overlay ─────────────────────────────────────────────────────────────

class _Toast(QLabel):
    """Slide-up toast that auto-dismisses after _TOAST_MS ms."""

    def __init__(self, parent: QWidget, msg: str, kind: str):
        super().__init__(parent)
        colors = {
            "info":    (SURFACE2, ACCENT),
            "success": ("#0a2a1a", GREEN),
            "error":   ("#2a0a0a", RED),
            "warning": ("#2a1800", ORANGE),
        }
        bg, fg = colors.get(kind, colors["info"])
        self.setText(f"  {msg}  ")
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; font-size: 9pt;"
            f"padding: 6px 12px; border: 1px solid {fg}; border-radius: 4px;"
        )
        self.adjustSize()
        self._target_y = parent.height() - self.height() - 116
        self._cur_y    = parent.height() - self.height() - 80
        self.move(parent.width() - self.width() - 20, self._cur_y)
        self.raise_()
        self.show()

        # Slide animation
        self._frame = 0
        self._anim  = QTimer(self)
        self._anim.timeout.connect(self._slide)
        self._anim.start(_TOAST_SLIDE_MS)

    def _slide(self):
        if self._frame < _TOAST_FRAMES:
            progress = self._frame / _TOAST_FRAMES
            y = int(self._cur_y + (self._target_y - self._cur_y) * progress)
            self.move(self.x(), y)
            self._frame += 1
        else:
            self._anim.stop()
            self.move(self.x(), self._target_y)
            QTimer.singleShot(_TOAST_MS, self._dismiss)

    def _dismiss(self):
        self.hide()
        self.deleteLater()


# ── Search history popup ──────────────────────────────────────────────────────

class _HistoryPopup(QWidget):
    item_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget, items: list[str], pos: QPoint):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(
            f"background: {SURFACE2}; border: 1px solid {BORDER};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for term in items[:8]:
            row = QWidget()
            row.setStyleSheet(f"background: {SURFACE2};")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)
            icon = QLabel("🕐")
            icon.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9pt; background: transparent;")
            rl.addWidget(icon)
            lbl = QLabel(term)
            lbl.setStyleSheet(f"color: {TEXT}; font-size: 9pt; background: transparent;")
            rl.addWidget(lbl, stretch=1)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            _term = term
            row.mousePressEvent = lambda _e, t=_term: self._pick(t)
            row.enterEvent = lambda _e, r=row: r.setStyleSheet(f"background: {SURFACE};")
            row.leaveEvent = lambda _e, r=row: r.setStyleSheet(f"background: {SURFACE2};")
            layout.addWidget(row)
        self.adjustSize()
        self.move(pos)
        self.show()

    def _pick(self, term: str):
        self.item_selected.emit(term)
        self.close()


# ── Main window ───────────────────────────────────────────────────────────────

class RadioUI(QMainWindow):
    # Signals for background-thread → main-thread communication
    _stations_ready = pyqtSignal(list, int)
    _logo_ready     = pyqtSignal(object, object)   # (widget_ref, QPixmap)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Radio Pro v12")
        self.setMinimumSize(920, 620)

        session = load_session()

        # Restore geometry
        geom = session.get("window_geometry")
        if geom:
            try:
                self.restoreGeometry(bytes.fromhex(geom))
            except Exception:
                self.resize(1160, 760)
        else:
            self.resize(1160, 760)

        # Session state
        self._session_volume  = session.get("volume",                70)
        self._session_cat     = session.get("last_cat",              "top")
        self._session_eq      = session.get("eq_preset",             "None")
        self._session_eq_on   = session.get("eq_enabled",            False)
        self._session_sort    = session.get("sort_idx",              0)
        self._session_aot     = session.get("always_on_top",         False)
        self._session_station = session.get("last_station",          None)
        self._search_history  = session.get("search_history",        [])
        # notifications removed in v12

        self.player   = RadioPlayer(on_permanent_failure=self._on_permanent_failure)
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

        self.all_stations: list[dict] = []
        self.stations:     list[dict] = []

        self._mem_lock   = threading.Lock()
        self._mem_cache: dict[str, QPixmap] = {}
        self._mem_keys:  list[str]          = []
        # URLs that permanently failed (403, DNS, 404) — never retry in this session
        self._failed_logo_cache: set[str]   = set()

        self.favorites: list[dict] = load_favorites()
        self._fav_urls: set[str]   = {s["url"] for s in self.favorites}
        self.recent:    list[dict] = load_recent()

        self.current_station: dict | None = None
        self.current_cat      = self._session_cat
        self._muted           = False
        self._sort_idx        = self._session_sort
        self._always_on_top   = False
        self._mini_player: MiniPlayer | None = None
        self._mini_logo_pixmap: QPixmap | None = None

        # Generation counters (cancel stale callbacks)
        self._play_gen  = 0
        self._fetch_gen = 0

        # Timers that need cancel handles
        self._debounce_timer  = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_search)

        self._spinner_timer  = QTimer(self)
        self._spinner_timer.timeout.connect(self._tick_spin)
        self._spin_step      = 0

        self._icy_full_text    = ""
        self._icy_offset       = 0
        self._marquee_timer    = QTimer(self)
        self._marquee_timer.timeout.connect(self._tick_marquee)

        self._play_start   = 0.0
        self._sleep_end: float | None           = None
        self._sleep_thread: threading.Timer | None = None

        self._resume_timer = QTimer(self)
        self._resume_timer.setSingleShot(True)
        self._resume_timer.timeout.connect(self._auto_resume_last_station)

        self._current_toast: _Toast | None = None
        self._hist_popup: _HistoryPopup | None = None

        # Pre-built default logos
        self.default_logo       = _make_default_logo(LOGO_SZ)
        self.default_logo_small = _make_default_logo(THUMB_SZ)
        self.default_logo_mini  = _make_default_logo(MINI_LOGO_SZ)

        # Wire internal signals
        self._stations_ready.connect(self._on_stations_loaded)
        self._logo_ready.connect(self._on_logo_ready)

        # Build UI
        self._build_ui()
        self._configure_shortcuts()

        # Apply session settings
        if self._session_aot:
            self._toggle_always_on_top(silent=True)

        self._vol_slider.setValue(self._session_volume)
        self.player.set_volume(self._session_volume)
        self._vol_lbl.setText(f"{self._session_volume}%")

        if self._session_eq_on and self._session_eq != "None":
            self.player.set_equalizer_preset(self._session_eq)
            self.player.toggle_equalizer(True)

        self._show_loading()
        self._switch_to_cat(self._session_cat)

        threading.Thread(target=preload_categories, args=(self._session_cat,),
                         daemon=True, name="preload").start()
        threading.Thread(target=db_vacuum, daemon=True, name="db-vacuum").start()

        # FEAT-1: Auto-resume
        if AUTO_RESUME and self._session_station:
            self._resume_timer.start(AUTO_RESUME_DELAY)

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._resume_timer.stop()
        self._cancel_sleep_timer()
        self._marquee_timer.stop()
        self._spinner_timer.stop()
        self._debounce_timer.stop()
        self._destroy_mini_player()

        if self.current_station and self._play_start:
            elapsed = int(time.time() - self._play_start)
            play_stats.record_listen_time(self.current_station["url"], elapsed)

        self.player.shutdown()
        # Cancel any still-queued logo-loading futures immediately (Python ≥ 3.9).
        # Running futures are not interrupted — their _logo_ready signals are
        # caught by _on_logo_ready which guards against deleted widgets.
        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python < 3.9 does not support cancel_futures
            self.executor.shutdown(wait=False)

        eq = self.player.equalizer
        save_session(
            volume                = self._vol_slider.value(),
            last_cat              = self.current_cat,
            eq_preset             = eq.current_preset,
            eq_enabled            = eq.enabled,
            sort_idx              = self._sort_idx,
            window_geometry       = self.saveGeometry().toHex().data().decode(),
            always_on_top         = self._always_on_top,
            last_station          = self.current_station,
            search_history        = self._search_history[:SEARCH_HISTORY_MAX],
            # notifications_enabled removed in v12
        )
        event.accept()

    def _on_permanent_failure(self, url: str):
        def _ui():
            self._now_title.setText("⚠  Connection lost")
            self._now_sub.setText("Could not reconnect — try another station")
            self._set_icy("")
            self._play_gen += 1
            self.spectrum.stop()
            self.current_station = None
            self._hide_badges()
            self._render_grid()
            self.toast("Connection lost — stream unreachable", kind="error")
        invoke_main(_ui)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _configure_shortcuts(self):
        def _sc(key, cb):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(cb)
        _sc("Space",     self._toggle_play)
        _sc("M",         self._toggle_mute)
        _sc("Ctrl+F",    self._focus_search)
        _sc("R",         self._refresh_current)
        _sc("?",         self._show_help)
        _sc("Ctrl+U",    self._open_add_station_dialog)
        _sc("N",         self._play_random)
        _sc("Left",      lambda: self._nav_station(-1))
        _sc("Right",     lambda: self._nav_station(+1))
        _sc("Up",        lambda: self._adjust_volume(+VOLUME_STEP))
        _sc("Down",      lambda: self._adjust_volume(-VOLUME_STEP))
        _sc("F",         self._fav_current)
        _sc("T",         self._toggle_always_on_top)
        _sc("Ctrl+M",    self._toggle_mini_player)
        _sc("Escape",    self._on_escape)

    def _on_escape(self):
        self._cancel_auto_resume()
        self._clear_search()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background: {BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)
        self._build_tab_bar(root)
        self._build_content(root)
        self._build_now_bar(root)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self, root: QVBoxLayout):
        hdr = QWidget()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {SURFACE};")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(18, 0, 18, 0)
        hdr_layout.setSpacing(0)

        # Brand
        brand = QWidget()
        brand.setStyleSheet(f"background: {SURFACE};")
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        dot = QLabel("◉")
        dot.setStyleSheet(f"color: {ACCENT}; background: transparent; font-size: 12pt; font-weight: bold; padding-right: 8px;")
        bl.addWidget(dot)
        name_lbl = QLabel("Smart Radio")
        name_lbl.setStyleSheet(f"color: {TEXT}; background: transparent; font-size: 13pt; font-weight: bold; letter-spacing: 0.5px;")
        bl.addWidget(name_lbl)
        pro_lbl = QLabel(" PRO")
        pro_lbl.setStyleSheet(f"color: {ACCENT2}; background: transparent; font-size: 8pt; font-weight: bold; padding-top: 5px;")
        bl.addWidget(pro_lbl)
        ver_lbl = QLabel(" v12")
        ver_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 7pt; padding-top: 6px;")
        bl.addWidget(ver_lbl)
        hdr_layout.addWidget(brand)
        hdr_layout.addStretch()

        # Search bar
        # Search wrapper — centred pill with focus glow via stylesheet toggle
        search_wrap = QWidget()
        search_wrap.setFixedHeight(36)
        search_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        search_wrap.setStyleSheet(
            f"background: {SURFACE2}; border: 1.5px solid {BORDER2}; border-radius: 18px;"
        )
        sw_layout = QHBoxLayout(search_wrap)
        sw_layout.setContentsMargins(12, 0, 8, 0)
        sw_layout.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 10pt;")
        sw_layout.addWidget(search_icon)

        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Search stations…")
        self._search_entry.setFixedWidth(260)
        self._search_entry.setStyleSheet(
            f"background: transparent; color: {TEXT}; border: none;"
            "font-size: 9.5pt; padding: 0; letter-spacing: 0.2px;")
        self._search_entry.textChanged.connect(self._on_search_changed)
        self._search_entry.returnPressed.connect(self._commit_search)

        # Store the wrap reference so focus events can update its border colour
        self._search_wrap = search_wrap

        def _focus_in(ev):
            type(self._search_entry).focusInEvent(self._search_entry, ev)
            self._search_wrap.setStyleSheet(
                f"background: {SURFACE2}; border: 1.5px solid {ACCENT}; border-radius: 18px;")
            self._show_hist_popup()

        def _focus_out(ev):
            type(self._search_entry).focusOutEvent(self._search_entry, ev)
            self._search_wrap.setStyleSheet(
                f"background: {SURFACE2}; border: 1.5px solid {BORDER2}; border-radius: 18px;")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._hide_hist_popup)

        self._search_entry.focusInEvent  = _focus_in
        self._search_entry.focusOutEvent = _focus_out
        sw_layout.addWidget(self._search_entry)

        self._clr_btn = QLabel("×")
        self._clr_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 14pt; padding: 0 4px;")
        self._clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clr_btn.mousePressEvent = lambda _e: self._clear_search()
        self._clr_btn.hide()
        sw_layout.addWidget(self._clr_btn)

        hdr_layout.addStretch()
        hdr_layout.addWidget(search_wrap)
        hdr_layout.addStretch()

        # Right controls
        right = QWidget()
        right.setStyleSheet(f"background: {SURFACE};")
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        def _hicon(text, cb, fg=TEXT_DIM, size=12, tip=""):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {fg}; background: transparent; font-size: {size}pt; padding: 0 6px;")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda _e: cb()
            lbl.enterEvent = lambda _e: lbl.setStyleSheet(
                f"color: {ACCENT}; background: transparent; font-size: {size}pt; padding: 0 6px;")
            lbl.leaveEvent = lambda _e: lbl.setStyleSheet(
                f"color: {fg}; background: transparent; font-size: {size}pt; padding: 0 6px;")
            if tip:
                lbl.setToolTip(tip)
            return lbl

        rl.addWidget(_hicon("＋", self._open_add_station_dialog, tip="Add custom station  (Ctrl+U)"))
        rl.addWidget(_hicon("?",  self._show_help, tip="Help & shortcuts  (?)"))

        self._mini_btn = _hicon("⧉", self._toggle_mini_player, size=13, tip="Toggle mini player  (Ctrl+M)")
        rl.addWidget(self._mini_btn)

        self._mute_lbl = QLabel("🔊")
        self._mute_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 12pt; padding: 0 4px;")
        self._mute_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_lbl.setToolTip("Toggle mute  (M)")
        self._mute_lbl.mousePressEvent = lambda _e: self._toggle_mute()
        rl.addWidget(self._mute_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedWidth(100)
        self._vol_slider.setToolTip("Volume  (↑↓ keys or scroll wheel)")
        # FIX v11: Use positive groove margins instead of negative handle margins.
        # Qt 6 on Windows rejects negative margin-top/margin-bottom on QSlider
        # handles and prints "Could not parse stylesheet" twice per slider.
        # Positive groove margins achieve the same thin-track look with zero warnings.
        self._vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {SURFACE2}; height: 4px; border: none; "
            "margin-top: 5px; margin-bottom: 5px; }} "
            f"QSlider::handle:horizontal {{ background: {ACCENT}; width: 13px; height: 13px; "
            "border: none; border-radius: 6px; }}"
        )
        self._vol_slider.valueChanged.connect(self._set_volume)
        rl.addWidget(self._vol_slider)

        self._vol_lbl = QLabel("70%")
        self._vol_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 8pt; padding: 0 4px;")
        self._vol_lbl.setFixedWidth(36)
        rl.addWidget(self._vol_lbl)

        hdr_layout.addWidget(right)
        root.addWidget(hdr)

        # FEAT-2: mouse-wheel volume on header
        hdr.wheelEvent = self._wheel_volume
        right.wheelEvent = self._wheel_volume

    # ── Tab bar ───────────────────────────────────────────────────────────────

    def _build_tab_bar(self, root: QVBoxLayout):
        tab_bar = QWidget()
        tab_bar.setFixedHeight(44)
        tab_bar.setStyleSheet(f"background: {SURFACE2}; border-bottom: 1px solid {BORDER};")
        tb_layout = QHBoxLayout(tab_bar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(0)
        tb_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._tab_btns: dict[str, QLabel] = {}
        self._active_tab: QLabel | None = None

        for label, cat in CATEGORIES:
            btn = QLabel(label)
            btn.setFixedHeight(40)
            btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn.setContentsMargins(18, 0, 18, 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 9pt; letter-spacing: 0.3px; padding: 0 18px;")
            _cat = cat
            _btn = btn
            btn.mousePressEvent = lambda _e, c=_cat, b=_btn: self._on_tab(c, b)
            btn.enterEvent = lambda _e, b=_btn: (
                b.setStyleSheet(
                    f"color: {TEXT}; background: transparent; font-size: 9pt; letter-spacing: 0.3px; padding: 0 18px;")
                if b != self._active_tab else None
            )
            btn.leaveEvent = lambda _e, b=_btn: (
                b.setStyleSheet(
                    f"color: {TEXT_DIM}; background: transparent; font-size: 9pt; letter-spacing: 0.3px; padding: 0 18px;")
                if b != self._active_tab else None
            )
            self._tab_btns[cat] = btn
            tb_layout.addWidget(btn)

        tb_layout.addStretch()
        root.addWidget(tab_bar)

        start = self._session_cat if self._session_cat in self._tab_btns else "top"
        self._activate_tab(self._tab_btns[start])

    def _activate_tab(self, btn: QLabel):
        if self._active_tab:
            self._active_tab.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 9pt; letter-spacing: 0.3px; padding: 0 18px;")
        btn.setStyleSheet(
            f"color: {ACCENT}; background: transparent; font-size: 9pt; font-weight: bold; letter-spacing: 0.3px; padding: 0 18px; border-bottom: 2px solid {ACCENT};")
        self._active_tab = btn

    def _on_tab(self, cat: str, btn: QLabel):
        if self.current_cat == cat and cat not in ("favorites", "recent"):
            return
        self._activate_tab(btn)
        self.current_cat = cat
        self._sort_idx   = 0
        self._clear_search(render=False)
        self._switch_to_cat(cat)

    def _switch_to_cat(self, cat: str):
        if cat == "favorites":
            self._show_favorites()
        elif cat == "recent":
            self._show_recent()
        else:
            self._show_loading()
            self._fetch(cat)

    # ── Content area (scrollable) ─────────────────────────────────────────────

    def _build_content(self, root: QVBoxLayout):
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # FIX v8: spaces between adjacent QSS rule blocks
        self._scroll_area.setStyleSheet(
            f"QScrollArea {{ background: {BG}; border: none; }} "
            f"QScrollBar:vertical {{ background: {BG}; width: 4px; margin: 0; }} "
            f"QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 2px; min-height: 30px; }} "
            f"QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }} "
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}"
        )
        self._scroll_area.wheelEvent = self._wheel_scroll

        self._content_widget = QWidget()
        self._content_widget.setStyleSheet(f"background: {BG};")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll_area.setWidget(self._content_widget)
        root.addWidget(self._scroll_area, stretch=1)

    def _wheel_scroll(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        sb = self._scroll_area.verticalScrollBar()
        sb.setValue(sb.value() - delta // 3)

    def _clear_content(self):
        # Remove all widgets from content layout
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── Now-playing bar ───────────────────────────────────────────────────────

    def _build_now_bar(self, root: QVBoxLayout):
        bar = QWidget()
        bar.setFixedHeight(104)
        bar.setStyleSheet(f"background: {NOW_BAR};")
        bar.wheelEvent = self._wheel_volume

        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)

        # Top accent line
        accent_line = QFrame()
        accent_line.setFixedHeight(2)
        accent_line.setStyleSheet(f"background: {ACCENT};")
        bar_layout.addWidget(accent_line)

        inner = QWidget()
        inner.setStyleSheet(f"background: {NOW_BAR};")
        inner.wheelEvent = self._wheel_volume
        inner_layout = QHBoxLayout(inner)
        inner_layout.setContentsMargins(14, 0, 14, 0)
        inner_layout.setSpacing(0)

        # Thumbnail
        self._now_thumb = QLabel()
        self._now_thumb.setFixedSize(THUMB_SZ, THUMB_SZ)
        self._now_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._now_thumb.setStyleSheet(f"background: {NOW_BAR}; border-radius: 4px;")
        self._now_thumb.setPixmap(self.default_logo_small)
        self._now_thumb.setToolTip("Click for station info")
        self._now_thumb.mousePressEvent = lambda _e: (
            self._show_station_info(self.current_station)
            if self.current_station else None
        )
        self._now_thumb.enterEvent = lambda _e: (
            self._now_thumb.setStyleSheet(
                f"background: {SURFACE2}; border-radius: 4px; border: 1px solid {ACCENT};")
            if self.current_station else None
        )
        self._now_thumb.leaveEvent = lambda _e: (
            self._now_thumb.setStyleSheet(f"background: {NOW_BAR}; border-radius: 4px;")
        )
        self._now_thumb.setCursor(Qt.CursorShape.ArrowCursor)
        inner_layout.addWidget(self._now_thumb)
        inner_layout.addSpacing(12)

        # Spectrum — enlarged in v12 (174×80 px widget)
        self.spectrum = SpectrumWidget()
        inner_layout.addWidget(self.spectrum)
        inner_layout.addSpacing(14)

        # Station info column (name, sub-info, ICY, timer, state chip)
        info = QWidget()
        info.setStyleSheet(f"background: {NOW_BAR};")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 6, 0, 6)
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._now_title = QLabel("Nothing playing")
        self._now_title.setStyleSheet(
            f"color: {TEXT}; background: transparent; "
            "font-size: 11pt; font-weight: bold; letter-spacing: 0.3px;")
        info_layout.addWidget(self._now_title)

        self._now_sub = QLabel("Select a station to start listening")
        self._now_sub.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 8pt;")
        info_layout.addWidget(self._now_sub)

        self._now_icy = QLabel("")
        self._now_icy.setStyleSheet(
            f"color: {ACCENT2}; background: transparent; "
            "font-size: 8pt; font-style: italic;")
        self._now_icy.setMaximumWidth(420)
        info_layout.addWidget(self._now_icy)

        self._now_timer = QLabel("")
        self._now_timer.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 7pt;")
        info_layout.addWidget(self._now_timer)

        self._state_chip = QLabel("")
        self._state_chip.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; "
            "font-size: 7pt; letter-spacing: 0.2px;")
        info_layout.addWidget(self._state_chip)

        inner_layout.addWidget(info, stretch=1)

        # Right controls
        ctrl = QWidget()
        ctrl.setStyleSheet(f"background: {NOW_BAR};")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 4, 0)
        ctrl_layout.setSpacing(0)
        ctrl_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Badge area
        self._badge_area = QWidget()
        self._badge_area.setFixedSize(120, 20)
        self._badge_area.setStyleSheet(f"background: {NOW_BAR};")
        badge_layout = QHBoxLayout(self._badge_area)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._live_badge = QLabel(" ● LIVE ")
        self._live_badge.setStyleSheet(
            f"color: white; background: {RED}; font-size: 7pt; font-weight: bold; padding: 2px 5px;")
        self._live_badge.hide()
        badge_layout.addWidget(self._live_badge)

        self._buf_badge = QLabel(" ⟳ BUFFERING ")
        self._buf_badge.setStyleSheet(
            f"color: black; background: {ORANGE}; font-size: 7pt; font-weight: bold; padding: 2px 5px;")
        self._buf_badge.hide()
        badge_layout.addWidget(self._buf_badge)

        ctrl_layout.addWidget(self._badge_area)

        def _ctrl_icon(text, cb, size=17):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: {size}pt; padding: 0 8px;")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda _e: cb()
            lbl.enterEvent = lambda _e: lbl.setStyleSheet(
                f"color: {TEXT}; background: transparent; font-size: {size}pt; padding: 0 8px;")
            lbl.leaveEvent = lambda _e: lbl.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: {size}pt; padding: 0 8px;")
            return lbl

        ctrl_layout.addSpacing(4)
        ctrl_layout.addWidget(_ctrl_icon("⏹", self._stop, size=16))
        ctrl_layout.addSpacing(4)

        self._eq_btn = QLabel("EQ")
        self._eq_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; font-weight: bold;"
            "padding: 4px 10px; border-radius: 4px;")
        self._eq_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eq_btn.setToolTip("Equalizer")
        self._eq_btn.mousePressEvent = lambda _e: self._open_eq_panel()
        self._eq_btn.enterEvent = lambda _e: self._eq_btn.setStyleSheet(
            f"color: {ACCENT}; background: {SURFACE2}; font-size: 8pt; font-weight: bold;"
            "padding: 4px 10px; border-radius: 4px;")
        self._eq_btn.leaveEvent = lambda _e: self._eq_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; font-weight: bold;"
            "padding: 4px 10px; border-radius: 4px;")
        ctrl_layout.addWidget(self._eq_btn)
        ctrl_layout.addSpacing(6)

        self._sleep_btn = _ctrl_icon("⏱", self._open_sleep_dialog, size=14)
        self._sleep_btn.setToolTip("Sleep timer")
        ctrl_layout.addWidget(self._sleep_btn)
        ctrl_layout.addSpacing(4)

        inner_layout.addWidget(ctrl)

        hint = QLabel("Space·stop  M·mute  F·fav  Ctrl+M·mini  ↑↓·vol  ←→·nav  ?·help")
        hint.setStyleSheet(
            f"color: #25304a; background: transparent; font-size: 7pt; padding: 0 12px;")
        inner_layout.addWidget(hint)

        bar_layout.addWidget(inner)
        root.addWidget(bar)

    # ── Badge helpers ─────────────────────────────────────────────────────────

    def _show_live_badge(self):
        self._buf_badge.hide()
        self._live_badge.show()

    def _show_buf_badge(self):
        self._live_badge.hide()
        self._buf_badge.show()

    def _hide_badges(self):
        self._live_badge.hide()
        self._buf_badge.hide()

    # ── Loading / Empty states ────────────────────────────────────────────────

    def _show_loading(self):
        if not self.current_station:
            self.spectrum.stop()
        self._clear_content()
        self._spin_step = 0

        wrap = QWidget()
        wrap.setStyleSheet(f"background: {BG};")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addSpacing(60)

        # Animated spinner — large glowing symbol
        self._spin_lbl = QLabel("◎")
        self._spin_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin_lbl.setStyleSheet(
            f"color: {ACCENT}; background: transparent; "
            "font-size: 42pt; letter-spacing: 2px;")
        wl.addWidget(self._spin_lbl)

        # Dot-pulse sub-label
        self._spin_dot_lbl = QLabel("● ○ ○")
        self._spin_dot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin_dot_lbl.setStyleSheet(
            f"color: {ACCENT}; background: transparent; "
            "font-size: 10pt; letter-spacing: 6px; padding-top: 8px;")
        wl.addWidget(self._spin_dot_lbl)

        load_txt = QLabel("Loading stations…")
        load_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        load_txt.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; "
            "font-size: 9pt; padding-top: 10px;")
        wl.addWidget(load_txt)

        self._content_layout.addWidget(wrap)
        self._spinner_timer.start(SPINNER_MS)

    def _tick_spin(self):
        # Ring frames give a smooth rotating feel
        ring_frames = ["◎", "◉", "●", "◉"]
        dot_frames  = [
            "● ○ ○",
            "○ ● ○",
            "○ ○ ●",
            "○ ● ○",
        ]
        step = self._spin_step % 4
        if hasattr(self, "_spin_lbl") and self._spin_lbl:
            try:
                self._spin_lbl.setText(ring_frames[step])
            except RuntimeError:
                pass
        if hasattr(self, "_spin_dot_lbl") and self._spin_dot_lbl:
            try:
                self._spin_dot_lbl.setText(dot_frames[step])
            except RuntimeError:
                pass
        self._spin_step += 1

    def _stop_spinner(self):
        self._spinner_timer.stop()

    def _show_empty(self, msg="No stations found"):
        self._stop_spinner()
        self._clear_content()

        wrap = QWidget()
        wrap.setStyleSheet(f"background: {BG};")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addSpacing(80)

        icon = QLabel("📻")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: transparent; font-size: 36pt;")
        wl.addWidget(icon)

        title = QLabel(msg)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {TEXT}; background: transparent; font-size: 13pt; font-weight: bold;")
        wl.addWidget(title)

        sub = QLabel("Try a different search or category")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 9pt; padding-top: 4px;")
        wl.addWidget(sub)

        self._content_layout.addWidget(wrap)

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch(self, category: str):
        self._fetch_gen += 1
        gen = self._fetch_gen
        def task():
            stations = fetch_category(category)
            self._stations_ready.emit(stations, gen)
        self.executor.submit(task)

    def _on_stations_loaded(self, stations: list[dict], gen: int):
        if gen != self._fetch_gen:
            return
        self._stop_spinner()
        self.all_stations = stations
        self.stations     = stations[:]
        if stations:
            self._apply_sort_and_render()
        else:
            self._show_empty()

    def _show_favorites(self):
        self._stop_spinner()
        self.all_stations = list(self.favorites)
        self.stations     = list(self.favorites)
        if not self.favorites:
            self._show_empty("No favourites yet — heart a station!")
        else:
            self._apply_sort_and_render()

    def _show_recent(self):
        self._stop_spinner()
        self.all_stations = list(self.recent)
        self.stations     = list(self.recent)
        if not self.recent:
            self._show_empty("Nothing played recently yet")
        else:
            self._render_recent_grid()

    # ── Sort & Render ─────────────────────────────────────────────────────────

    def _apply_sort_and_render(self):
        label, key, reverse = SORT_OPTIONS[self._sort_idx]
        if key is None:
            self.stations = self.all_stations[:]
        elif key == "name":
            self.stations = sorted(self.all_stations,
                key=lambda s: _clean_name(s.get("name", "")).lower(), reverse=reverse)
        elif key == "_plays":
            self.stations = sorted(self.all_stations,
                key=lambda s: play_stats.get_play_count(s.get("url", "")), reverse=True)
        else:
            self.stations = sorted(self.all_stations,
                key=lambda s: s.get(key, 0), reverse=reverse)
        self._render_grid()

    def _render_grid(self):
        self._stop_spinner()
        self._clear_content()
        self._scroll_area.verticalScrollBar().setValue(0)

        display     = self.stations[:MAX_RESULTS]
        total       = len(self.all_stations)
        count       = len(display)
        current_url = self.current_station.get("url") if self.current_station else None

        # Header row (refresh + sort + count)
        hdr = QWidget()
        hdr.setStyleSheet(f"background: {BG};")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 14, 20, 6)
        hdr_layout.setSpacing(12)

        refresh_btn = QLabel("↻  Refresh")
        refresh_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.mousePressEvent = lambda _e: self._refresh_current()
        refresh_btn.enterEvent = lambda _e: refresh_btn.setStyleSheet(
            f"color: {ACCENT}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        refresh_btn.leaveEvent = lambda _e: refresh_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        hdr_layout.addWidget(refresh_btn)

        sort_lbl = QLabel("Sort:")
        sort_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 8pt;")
        hdr_layout.addWidget(sort_lbl)

        for i, (lbl, _, _) in enumerate(SORT_OPTIONS):
            active = (i == self._sort_idx)
            sb = QLabel(lbl)
            sb.setStyleSheet(
                f"color: {ACCENT if active else TEXT_DIM};"
                f"background: {SURFACE2 if active else BG};"
                f"font-size: 8pt; {'font-weight: bold;' if active else ''}"
                "padding: 2px 6px; border-radius: 3px;")
            sb.setCursor(Qt.CursorShape.PointingHandCursor)
            _i = i
            sb.mousePressEvent = lambda _e, idx=_i: self._set_sort(idx)
            hdr_layout.addWidget(sb)

        hdr_layout.addStretch()
        shown = f"Showing {count}" if count == total else f"Showing {count} of {total}"
        count_lbl = QLabel(shown)
        count_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 8pt;")
        hdr_layout.addWidget(count_lbl)

        self._content_layout.addWidget(hdr)

        # Grid of cards
        grid_wrap = QWidget()
        grid_wrap.setStyleSheet(f"background: {BG};")
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(14, 0, 14, 16)
        grid.setSpacing(10)

        for i, s in enumerate(display):
            playing = (s["url"] == current_url)
            card = StationCard(s, s["url"] in self._fav_urls, playing)
            card.play_clicked.connect(self._play)
            card.fav_clicked.connect(self._toggle_fav_card)
            card.right_clicked.connect(self._card_context_menu)
            card.double_clicked.connect(self._show_station_info)
            grid.addWidget(card, i // COLS, i % COLS, Qt.AlignmentFlag.AlignTop)

            # FEAT-14: play-count badge
            if STATS_ENABLED:
                pc = play_stats.get_play_count(s.get("url", ""))
                if pc > 0:
                    card.add_play_badge(pc)

            self._load_logo(s.get("logo", ""), card, LOGO_SZ)

        for c in range(COLS):
            grid.setColumnStretch(c, 1)

        self._content_layout.addWidget(grid_wrap)
        self._content_layout.addStretch()

    def _render_recent_grid(self):
        self._stop_spinner()
        self._clear_content()
        self._scroll_area.verticalScrollBar().setValue(0)

        current_url = self.current_station.get("url") if self.current_station else None

        hdr = QWidget()
        hdr.setStyleSheet(f"background: {BG};")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 14, 20, 6)

        hdr_lbl = QLabel(f"Recently Played  ({len(self.recent)} stations)")
        hdr_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 9pt;")
        hdr_layout.addWidget(hdr_lbl)
        hdr_layout.addStretch()

        clr_btn = QLabel("✕  Clear History")
        clr_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clr_btn.mousePressEvent = lambda _e: self._clear_recent()
        clr_btn.enterEvent = lambda _e: clr_btn.setStyleSheet(
            f"color: {RED}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        clr_btn.leaveEvent = lambda _e: clr_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: {SURFACE2}; font-size: 8pt; padding: 3px 8px; border-radius: 3px;")
        hdr_layout.addWidget(clr_btn)
        self._content_layout.addWidget(hdr)

        grid_wrap = QWidget()
        grid_wrap.setStyleSheet(f"background: {BG};")
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(14, 0, 14, 16)
        grid.setSpacing(10)

        for i, s in enumerate(self.stations[:MAX_RESULTS]):
            playing = (s["url"] == current_url)
            card = StationCard(s, s["url"] in self._fav_urls, playing)
            card.play_clicked.connect(self._play)
            card.fav_clicked.connect(self._toggle_fav_card)
            card.right_clicked.connect(self._card_context_menu)
            card.double_clicked.connect(self._show_station_info)
            grid.addWidget(card, i // COLS, i % COLS, Qt.AlignmentFlag.AlignTop)
            self._load_logo(s.get("logo", ""), card, LOGO_SZ)
            ts = s.get("played_at")
            if ts:
                ago_lbl = QLabel(_ago(ts), card)
                ago_lbl.setStyleSheet(
                    f"color: #3d4f66; background: {SURFACE}; font-size: 6pt;")
                ago_lbl.move(148, 6)
                ago_lbl.show()

        for c in range(COLS):
            grid.setColumnStretch(c, 1)

        self._content_layout.addWidget(grid_wrap)
        self._content_layout.addStretch()

    def _clear_recent(self):
        if QMessageBox.question(self, "Clear History",
                                "Remove all recently played stations?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        self.recent = self.all_stations = self.stations = []
        save_recent(self.recent)
        self._show_empty("Nothing played recently yet")
        self.toast("Recent history cleared")

    def _set_sort(self, idx: int):
        self._sort_idx = idx
        self._apply_sort_and_render()

    def _refresh_current(self):
        cat = self.current_cat
        if cat in ("favorites", "recent"):
            self._switch_to_cat(cat)
            return
        self._show_loading()
        self._fetch_gen += 1
        gen = self._fetch_gen
        def task():
            stations = fetch_category(cat, use_cache=False)
            self._stations_ready.emit(stations, gen)
        self.executor.submit(task)
        self.toast("Refreshing stations…")

    # ── Logo loading ──────────────────────────────────────────────────────────

    def _load_logo(self, url: str, card: StationCard, size: int):
        default = (self.default_logo if size == LOGO_SZ
                   else self.default_logo_mini if size == MINI_LOGO_SZ
                   else self.default_logo_small)
        if not url:
            card.set_logo(default)
            return
        # Skip URLs that permanently failed this session (403, DNS, 404, SVG, etc.)
        if url in self._failed_logo_cache:
            card.set_logo(default)
            return
        key = f"{url}@{size}"
        with self._mem_lock:
            if key in self._mem_cache:
                card.set_logo(self._mem_cache[key])
                return

        _card_ref = card

        def task():
            # Double-check inside the task: another thread may have already marked
            # this URL as failed between the time the task was queued and now.
            if url in self._failed_logo_cache:
                self._logo_ready.emit(_card_ref, default)
                return
            try:
                raw_bytes = db_logo_get(url, size)
                from_db   = raw_bytes is not None
                if not from_db:
                    # Use the shared logo session (connection pooling, no retry)
                    # instead of bare requests.get() — avoids a new TCP connection
                    # per logo and keeps the API session's retry budget clean.
                    r = get_logo_session().get(
                        url, timeout=LOGO_TIMEOUT, verify=True, stream=True)
                    r.raise_for_status()
                    raw_bytes = r.raw.read(LOGO_MAX_BYTES, decode_content=True)
                img  = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                img  = img.resize((size, size), Image.LANCZOS)
                mask = Image.new("L", (size, size), 0)
                ImageDraw.Draw(mask).ellipse((1, 1, size - 1, size - 1), fill=255)
                out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                out.paste(img, mask=mask)
                if not from_db:
                    buf = io.BytesIO()
                    out.save(buf, format="PNG")
                    db_logo_put(url, size, buf.getvalue())
                pixmap = _pil_to_qpixmap(out)
                with self._mem_lock:
                    self._mem_cache[key] = pixmap
                    self._mem_keys.append(key)
                    purge_mem_logo_cache(self._mem_cache, self._mem_keys, MEM_CACHE_MAX)
                self._logo_ready.emit(_card_ref, pixmap)
            except Exception as e:
                log(f"Logo load failed ({url!r}): {e}", "debug")
                # Mark URL as permanently failed — skipped on all future renders
                self._failed_logo_cache.add(url)
                self._logo_ready.emit(_card_ref, default)

        self.executor.submit(task)

    def _on_logo_ready(self, card_ref, pixmap):
        try:
            if card_ref and not card_ref.isHidden():
                card_ref.set_logo(pixmap)
        except RuntimeError:
            pass  # widget was deleted

    # ── Search ────────────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        if text.strip():
            self._clr_btn.show()
        else:
            self._clr_btn.hide()
        self._debounce_timer.start(DEBOUNCE_MS)

    def _do_search(self):
        q = self._search_entry.text().strip().lower()
        if not q:
            self.stations = self.all_stations[:]
        else:
            self.stations = [
                s for s in self.all_stations
                if q in s.get("name",     "").lower()
                or q in s.get("country",  "").lower()
                or q in s.get("tags",     "").lower()
                or q in s.get("language", "").lower()
            ]
        if self.stations:
            self._render_grid()
        else:
            self._show_empty("No matches found")

    def _clear_search(self, render: bool = True):
        self._search_entry.blockSignals(True)
        self._search_entry.clear()
        self._search_entry.blockSignals(False)
        self._clr_btn.hide()
        self._hide_hist_popup()
        self.stations = self.all_stations[:]
        if render:
            self._apply_sort_and_render()

    def _focus_search(self):
        self._search_entry.setFocus()
        self._search_entry.selectAll()

    def _commit_search(self):
        q = self._search_entry.text().strip()
        if q:
            self._add_to_search_history(q)
        self._hide_hist_popup()

    def _add_to_search_history(self, term: str):
        h = [x for x in self._search_history if x.lower() != term.lower()]
        h.insert(0, term)
        self._search_history = h[:SEARCH_HISTORY_MAX]

    # ── Search history popup ──────────────────────────────────────────────────

    def _show_hist_popup(self):
        self._hide_hist_popup()
        if not self._search_history:
            return
        # Position below search entry in global coords
        ge = self._search_entry.mapToGlobal(
            QPoint(0, self._search_entry.height() + 2))
        # Convert to position relative to central widget
        local = self.centralWidget().mapFromGlobal(ge)
        popup = _HistoryPopup(self.centralWidget(), self._search_history, local)
        popup.item_selected.connect(self._pick_history)
        self._hist_popup = popup

    def _hide_hist_popup(self):
        if self._hist_popup:
            try:
                self._hist_popup.close()
            except Exception:
                pass
            self._hist_popup = None

    def _pick_history(self, term: str):
        self._search_entry.setText(term)
        self._do_search()
        self._hide_hist_popup()

    # ── Favorites ─────────────────────────────────────────────────────────────

    def _toggle_fav_card(self, station: dict):
        url = station["url"]
        if url in self._fav_urls:
            self.favorites  = [f for f in self.favorites if f["url"] != url]
            self._fav_urls.discard(url)
            self.toast("Removed from Favorites")
        else:
            self.favorites.append(station)
            self._fav_urls.add(url)
            self.toast(f"❤  {_clean_name(station.get('name',''))} added", kind="success")
        if not save_favorites(self.favorites):
            self.toast("⚠ Could not save favorites", kind="error")
        self._render_grid()

    def _fav_current(self):
        if not self.current_station:
            return
        url = self.current_station["url"]
        if url in self._fav_urls:
            self.favorites  = [f for f in self.favorites if f["url"] != url]
            self._fav_urls.discard(url)
            self.toast("Removed from Favorites")
        else:
            self.favorites.append(self.current_station)
            self._fav_urls.add(url)
            self.toast(f"❤  {_clean_name(self.current_station.get('name',''))} added",
                       kind="success")
        save_favorites(self.favorites)
        self._render_grid()

    def _export_favorites(self):
        if not self.favorites:
            QMessageBox.information(self, "Export", "No favorites to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Favorites", "radio_favorites.json",
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, indent=2, ensure_ascii=False)
            self.toast(f"Exported {len(self.favorites)} stations", kind="success")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _export_m3u(self):
        if not self.favorites:
            QMessageBox.information(self, "Export M3U", "No favorites to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as M3U Playlist", "radio_favorites.m3u",
            "M3U Playlist (*.m3u);;All (*.*)")
        if not path:
            return
        try:
            lines = ["#EXTM3U\n"]
            for s in self.favorites:
                name    = _clean_name(s.get("name", "Unknown"))
                bitrate = s.get("bitrate", 0) or -1
                country = s.get("country", "")
                logo    = s.get("logo", "")
                tvg     = f' tvg-logo="{logo}"' if logo else ""
                lines.append(
                    f'#EXTINF:{bitrate},{name} ({country})\n'
                    f'# group-title="{s.get("tags","").split(",")[0].strip()}"{tvg}\n'
                    f'{s["url"]}\n'
                )
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            self.toast(f"M3U exported: {len(self.favorites)} stations", kind="success")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _import_favorites(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Favorites", "", "JSON (*.json);;All (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array.")
            imported = [d for d in data if isinstance(d, dict) and d.get("url")]
            existing = {s["url"] for s in self.favorites}
            new_ones = [s for s in imported if s["url"] not in existing]
            self.favorites.extend(new_ones)
            self._fav_urls = {s["url"] for s in self.favorites}
            save_favorites(self.favorites)
            self.toast(f"Imported {len(new_ones)} stations "
                       f"({len(imported)-len(new_ones)} skipped)", kind="success")
            if self.current_cat == "favorites":
                self._show_favorites()
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", str(e))

    # ── Playback ──────────────────────────────────────────────────────────────

    def _play(self, station: dict, fade: bool = False):
        if (self.current_station
                and self.current_station["url"] == station["url"]
                and self.player.is_playing()):
            self._stop()
            return
        if self.current_station and self._play_start:
            elapsed = int(time.time() - self._play_start)
            if STATS_ENABLED:
                play_stats.record_listen_time(self.current_station["url"], elapsed)

        try:
            self.player.stop()
        except Exception as e:
            log(f"Pre-play stop error: {e}", "warning")

        success = self.player.play(station["url"])
        if not success:
            self._now_title.setText("⚠ Could not play this station")
            self._now_sub.setText("URL blocked or VLC error")
            self.toast("⚠ Could not play station", kind="error")
            return

        vol = self._vol_slider.value()
        if fade:
            self.player.fade_in(target_vol=vol)
        else:
            self.player.set_volume(vol)

        self.current_station = station
        self._update_now_bar(station)
        self.recent = add_to_recent(station, self.recent)
        save_recent(self.recent)

        if STATS_ENABLED:
            play_stats.record_play(station["url"], station.get("name", ""))

        self._render_grid()
        log(f"PLAY: {station.get('name', '?')}")
        # Mini logo is now pre-loaded in _update_now_bar unconditionally

    def _toggle_play(self):
        if self.current_station and self.player.is_playing():
            self._stop()
        elif self.recent:
            self._play(self.recent[0])

    def _stop(self):
        self._cancel_sleep_timer()

        def _do_stop():
            try:
                self.player.stop()
            except Exception as e:
                log(f"Stop error: {e}", "warning")

        if self.current_station and self.player.is_playing():
            self.player.fade_out(callback=_do_stop)
        else:
            _do_stop()

        if self.current_station and self._play_start and STATS_ENABLED:
            elapsed = int(time.time() - self._play_start)
            play_stats.record_listen_time(self.current_station["url"], elapsed)

        self.current_station = None
        self._play_gen += 1
        self._mini_logo_pixmap = None   # mini player reverts to default logo on stop
        self._set_icy("")
        self.spectrum.stop()
        self._now_title.setText("Nothing playing")
        self._now_sub.setText("Select a station to start listening")
        self._now_timer.setText("")
        self._state_chip.setText("")
        self._now_thumb.setPixmap(self.default_logo_small)
        self._now_thumb.setCursor(Qt.CursorShape.ArrowCursor)
        self._hide_badges()
        self._render_grid()

    def _play_random(self):
        if self.stations:
            self._play(random.choice(self.stations))

    def _nav_station(self, direction: int):
        if not self.stations:
            return
        display = self.stations[:MAX_RESULTS]
        if not display:
            return
        if self.current_station:
            try:
                idx = next(i for i, s in enumerate(display)
                           if s["url"] == self.current_station["url"])
            except StopIteration:
                idx = -1
            idx = (idx + direction) % len(display)
        else:
            idx = 0 if direction > 0 else len(display) - 1
        self._play(display[idx])

    def _auto_resume_last_station(self):
        st = self._session_station
        if st and isinstance(st, dict) and st.get("url"):
            log(f"Auto-resuming: {st.get('name','?')}", "info")
            self._play(st, fade=True)
            self.toast(f"▶  Resumed: {_clean_name(st.get('name',''))}", kind="info")

    def _cancel_auto_resume(self):
        self._resume_timer.stop()

    # ── Volume & Mute ─────────────────────────────────────────────────────────

    def _set_volume(self, val: int):
        self.player.set_volume(val)
        self._vol_lbl.setText(f"{val}%")

    def _adjust_volume(self, delta: int):
        new_vol = max(0, min(100, self._vol_slider.value() + delta))
        self._vol_slider.setValue(new_vol)

    def _wheel_volume(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self._adjust_volume(+VOLUME_STEP if delta > 0 else -VOLUME_STEP)

    def _toggle_mute(self):
        self._muted = self.player.toggle_mute()
        self._mute_lbl.setText("🔇" if self._muted else "🔊")
        self.toast("Muted" if self._muted else "Unmuted")

    # ── Now-bar update ────────────────────────────────────────────────────────

    def _update_now_bar(self, station: dict):
        self._play_gen += 1
        gen = self._play_gen

        name = _clean_name(station.get("name", ""))
        self._now_title.setText(name)
        self._now_thumb.setCursor(Qt.CursorShape.PointingHandCursor)

        country  = (station.get("country") or "").strip()
        tags_raw = (station.get("tags")    or "").strip()
        tag      = tags_raw.split(",")[0].strip() if tags_raw else ""
        bitrate  = station.get("bitrate", 0)
        codec    = (station.get("codec", "") or "").strip()
        parts    = list(filter(None, [country, tag]))
        if bitrate:
            qual = f"{bitrate}k"
            if codec and codec.upper() not in ("MP3", ""):
                qual += f" {codec.upper()}"
            parts.append(qual)
        self._now_sub.setText((" · ".join(parts)[:65] or "Live Radio"))
        self._set_icy("")
        self._show_live_badge()
        self._state_chip.setText("")

        logo = station.get("logo", "")
        if logo:
            self._load_thumb_logo(logo)
        else:
            self._now_thumb.setPixmap(self.default_logo_small)

        self._play_start = time.time()
        self.spectrum.start()
        self._mini_logo_pixmap = None
        # Always pre-load the mini logo so it's ready when mini player opens later
        if logo:
            self._load_mini_logo(logo)
        QTimer.singleShot(0, lambda: self._tick_timer(gen))
        QTimer.singleShot(0, lambda: self._tick_meta(gen))

    def _load_thumb_logo(self, url: str):
        def task():
            try:
                raw_bytes = db_logo_get(url, THUMB_SZ)
                from_db   = raw_bytes is not None
                if not from_db:
                    r         = requests.get(url, timeout=LOGO_TIMEOUT, verify=True, stream=True)
                    r.raise_for_status()
                    raw_bytes = r.raw.read(LOGO_MAX_BYTES, decode_content=True)
                img  = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                img  = img.resize((THUMB_SZ, THUMB_SZ), Image.LANCZOS)
                mask = Image.new("L", (THUMB_SZ, THUMB_SZ), 0)
                ImageDraw.Draw(mask).ellipse((1, 1, THUMB_SZ-1, THUMB_SZ-1), fill=255)
                out  = Image.new("RGBA", (THUMB_SZ, THUMB_SZ), (0, 0, 0, 0))
                out.paste(img, mask=mask)
                if not from_db:
                    buf = io.BytesIO()
                    out.save(buf, format="PNG")
                    db_logo_put(url, THUMB_SZ, buf.getvalue())
                pix = _pil_to_qpixmap(out)
                def _ui():
                    self._now_thumb.setPixmap(pix)
                invoke_main(_ui)
            except Exception:
                pass
        self.executor.submit(task)

    def _load_mini_logo(self, url: str):
        def task():
            try:
                raw_bytes = db_logo_get(url, MINI_LOGO_SZ)
                from_db   = raw_bytes is not None
                if not from_db:
                    r         = requests.get(url, timeout=LOGO_TIMEOUT, verify=True, stream=True)
                    r.raise_for_status()
                    raw_bytes = r.raw.read(LOGO_MAX_BYTES, decode_content=True)
                img  = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                img  = img.resize((MINI_LOGO_SZ, MINI_LOGO_SZ), Image.LANCZOS)
                mask = Image.new("L", (MINI_LOGO_SZ, MINI_LOGO_SZ), 0)
                ImageDraw.Draw(mask).ellipse(
                    (1, 1, MINI_LOGO_SZ-1, MINI_LOGO_SZ-1), fill=255)
                out  = Image.new("RGBA", (MINI_LOGO_SZ, MINI_LOGO_SZ), (0, 0, 0, 0))
                out.paste(img, mask=mask)
                # Cache to DB so next launch serves from disk (zero network cost)
                if not from_db:
                    buf = io.BytesIO()
                    out.save(buf, format="PNG")
                    db_logo_put(url, MINI_LOGO_SZ, buf.getvalue())
                pix  = _pil_to_qpixmap(out)
                def _ui():
                    self._mini_logo_pixmap = pix
                invoke_main(_ui)
            except Exception:
                pass
        self.executor.submit(task)

    # ── Tick loops ────────────────────────────────────────────────────────────

    def _tick_timer(self, gen: int):
        if gen != self._play_gen or not self.current_station:
            return
        state = self.player.get_state_label()
        if state == "reconnecting":
            count = self.player.get_reconnect_count()
            self._now_title.setText(f"↺  Reconnecting… ({count}/{MAX_RECONNECT})")
            self._hide_badges()
            self._state_chip.setText(f"attempt {count}/{MAX_RECONNECT}")
            self._state_chip.setStyleSheet(
                f"color: {ORANGE}; background: transparent; font-size: 7pt;")
        elif state in ("buffering", "opening"):
            self._show_buf_badge()
            if "↺" in self._now_title.text():
                self._now_title.setText(
                    _clean_name(self.current_station.get("name", "")))
            self._state_chip.setText("buffering…")
            self._state_chip.setStyleSheet(
                f"color: {ORANGE}; background: transparent; font-size: 7pt;")
        else:
            self._show_live_badge()
            if "↺" in self._now_title.text():
                self._now_title.setText(
                    _clean_name(self.current_station.get("name", "")))
            self._state_chip.setText("")

        elapsed  = int(time.time() - self._play_start)
        today_s  = play_stats.get_today_listen_time() + elapsed
        h, rem   = divmod(elapsed, 3600)
        m, s     = divmod(rem, 60)
        txt = f"On air  {h}h {m:02d}m {s:02d}s" if h else f"On air  {m}:{s:02d}"
        if today_s > elapsed + 10:
            th, tr = divmod(today_s, 3600)
            tm, ts = divmod(tr, 60)
            txt += f"    Session {th}h {tm:02d}m" if th else f"    Session {tm}m"
        if self._sleep_end is not None:
            remaining = max(0, int(self._sleep_end - time.time()))
            sr, ss    = divmod(remaining, 60)
            txt += f"    ⏱ Sleep in {sr}:{ss:02d}"
        self._now_timer.setText(txt)
        QTimer.singleShot(TIMER_MS, lambda: self._tick_timer(gen))

    def _tick_meta(self, gen: int):
        if gen != self._play_gen or not self.current_station:
            return
        try:
            meta  = self.player.get_current_metadata()
            track = meta.get("title", "").strip()
            self._set_icy(track)
            # (notifications removed in v12)
        except Exception:
            pass
        QTimer.singleShot(ICY_POLL_MS, lambda: self._tick_meta(gen))

    # ── ICY marquee ───────────────────────────────────────────────────────────

    def _set_icy(self, text: str):
        self._marquee_timer.stop()
        self._icy_offset = 0
        # Suppress raw stream-path slugs (e.g. "68snnbug8rhvv") that have
        # no spaces, are purely alphanumeric/hyphens, and are ≤ 22 chars.
        import re as _re
        _slug = (text or "").strip()
        _is_slug = (
            bool(_slug)
            and len(_slug) <= 22
            and " " not in _slug
            and bool(_re.fullmatch(r"[A-Za-z0-9_\-]+", _slug))
        )
        cleaned = "" if _is_slug else text
        self._icy_full_text = cleaned
        if not cleaned:
            self._now_icy.setText("")
            return
        MAX_CHARS = 42
        display   = f"♪  {cleaned}"
        if len(display) <= MAX_CHARS:
            self._now_icy.setText(display)
        else:
            self._icy_offset = 0
            self._marquee_timer.start(_MARQUEE_MS)

    def _tick_marquee(self):
        if not self._icy_full_text:
            return
        MAX_CHARS = 38
        full    = f"♪  {self._icy_full_text}    "
        visible = (full * 2)[self._icy_offset: self._icy_offset + MAX_CHARS]
        self._now_icy.setText(visible)
        self._icy_offset = (self._icy_offset + 1) % len(full)

    # ── Toast ─────────────────────────────────────────────────────────────────

    def toast(self, msg: str, kind: str = "info"):
        if self._current_toast:
            try:
                self._current_toast.hide()
                self._current_toast.deleteLater()
            except RuntimeError:
                pass
        self._current_toast = _Toast(self.centralWidget(), msg, kind)

    # ── v6 Features: Always-on-top, Mini-player ────────────────────────────────

    def _toggle_always_on_top(self, silent: bool = False):
        self._always_on_top = not self._always_on_top
        flags = self.windowFlags()
        if self._always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        else:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.show()  # must call show() after setWindowFlag
        if not silent:
            self.toast("Pinned on top" if self._always_on_top else "Unpinned")

    def _toggle_mini_player(self):
        if self._mini_player is not None:
            self._destroy_mini_player()
            self.show()
            self._mini_btn.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 13pt; padding: 0 6px;")
            return

        self._mini_player = MiniPlayer(
            self,
            on_expand        = self._expand_from_mini,
            on_mute          = self._toggle_mute,
            on_next          = lambda: self._nav_station(+1),
            on_volume_change = lambda v: (self._vol_slider.setValue(v),),
            get_volume       = self._vol_slider.value,
            get_station_name = lambda: (
                _clean_name(self.current_station.get("name", ""))
                if self.current_station else ""),
            get_icy_text     = lambda: self._icy_full_text,
            get_logo_pixmap  = lambda: self._mini_logo_pixmap,
            default_logo_pixmap = self.default_logo_mini,
            is_playing       = lambda: self.player.is_playing(),
            is_muted         = lambda: self._muted,
        )
        # Restore last saved position if available
        session = load_session()
        mini_pos = session.get("mini_pos")
        if mini_pos and isinstance(mini_pos, list) and len(mini_pos) == 2:
            self._mini_player.move(mini_pos[0], mini_pos[1])
        self._mini_player.show()
        self._mini_btn.setStyleSheet(
            f"color: {ACCENT}; background: transparent; font-size: 13pt; padding: 0 6px;")
        self.hide()

    def _expand_from_mini(self):
        self._destroy_mini_player()
        self.show()
        self.raise_()
        self._mini_btn.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 13pt; padding: 0 6px;")

    def _destroy_mini_player(self):
        if self._mini_player is not None:
            # Save current position so it restores next time
            pos = self._mini_player.pos()
            save_session(mini_pos=[pos.x(), pos.y()])
            self._mini_player.cleanup()
            self._mini_player.close()
            self._mini_player.deleteLater()
            self._mini_player = None

    # ── EQ Panel ──────────────────────────────────────────────────────────────

    def _open_eq_panel(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Equalizer")
        dlg.setFixedWidth(350)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Title row
        title_row = QHBoxLayout()
        title_lbl = QLabel("Equalizer")
        title_lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 10pt; font-weight: bold; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Enable checkbox
        enable_cb = QCheckBox("Enable EQ")
        enable_cb.setChecked(self.player.equalizer.enabled)
        enable_cb.setStyleSheet(
            f"color: {TEXT}; background: transparent; font-size: 9pt;")
        layout.addWidget(enable_cb)

        # EQ curve canvas
        class CurveWidget(QWidget):
            def __init__(self_c, eq_ref):
                super().__init__()
                self_c.setFixedSize(310, 56)
                self_c._eq = eq_ref
                self_c.setStyleSheet("background: #0a0d12;")
            def paintEvent(self_c, _):
                p = QPainter(self_c)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                W, H = 310, 56
                # Grid lines
                for frac in [0.25, 0.5, 0.75]:
                    y = int(H * frac)
                    p.setPen(QColor("#1a2a3a"))
                    p.drawLine(0, y, W, y)
                p.setPen(QColor("#2a3a4a"))
                p.drawLine(0, H//2, W, H//2)
                # EQ curve
                bands = self_c._eq.get_bands()
                n     = len(bands)
                color = ACCENT if self_c._eq.enabled else TEXT_DIM
                p.setPen(QColor(color))
                pts   = []
                for px in range(W):
                    frac   = px / (W - 1)
                    band_f = frac * (n - 1)
                    lo     = int(band_f)
                    hi     = min(lo + 1, n - 1)
                    t      = band_f - lo
                    gain   = bands[lo] * (1 - t) + bands[hi] * t
                    y = int(H / 2 - gain * (H / 2) / 20)
                    y = max(2, min(H - 2, y))
                    if pts:
                        p.drawLine(pts[-1][0], pts[-1][1], px, y)
                    pts.append((px, y))
                p.end()

        curve = CurveWidget(self.player.equalizer)
        layout.addWidget(curve)

        # Preset buttons
        preset_lbl = QLabel("Presets")
        preset_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 7pt; background: transparent;")
        preset_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preset_lbl)

        preset_names = [n for n in Equalizer.PRESETS.keys() if n != "Custom"]
        preset_grid  = QWidget()
        preset_grid.setStyleSheet(f"background: {SURFACE};")
        pg_layout    = QGridLayout(preset_grid)
        pg_layout.setSpacing(4)
        pg_layout.setContentsMargins(0, 0, 0, 0)
        preset_btns  = []

        def _refresh_presets():
            cp = self.player.equalizer.current_preset
            en = self.player.equalizer.enabled
            for btn_lbl, name in preset_btns:
                active = (cp == name) and en
                btn_lbl.setStyleSheet(
                    f"color: {'black' if active else TEXT_DIM};"
                    f"background: {ACCENT if active else SURFACE2};"
                    "font-size: 8pt; padding: 3px 7px; border-radius: 3px;")
            self._eq_btn.setStyleSheet(
                f"color: {ACCENT if en and cp != 'None' else TEXT_DIM};"
                f"background: {SURFACE2}; font-size: 8pt; font-weight: bold;"
                "padding: 3px 8px; border-radius: 2px;")
            curve.update()

        def _select_preset(name: str):
            self.player.set_equalizer_preset(name)
            if not self.player.equalizer.enabled:
                self.player.toggle_equalizer(True)
                enable_cb.setChecked(True)
            _sync_sliders()
            _refresh_presets()

        for idx, name in enumerate(preset_names):
            active = (self.player.equalizer.current_preset == name
                      and self.player.equalizer.enabled)
            btn_lbl = QLabel(name)
            btn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_lbl.setStyleSheet(
                f"color: {'black' if active else TEXT_DIM};"
                f"background: {ACCENT if active else SURFACE2};"
                "font-size: 8pt; padding: 3px 7px; border-radius: 3px;")
            btn_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            _name = name
            btn_lbl.mousePressEvent = lambda _e, n=_name: _select_preset(n)
            pg_layout.addWidget(btn_lbl, idx // 4, idx % 4)
            preset_btns.append((btn_lbl, name))
        for c in range(4):
            pg_layout.setColumnStretch(c, 1)
        layout.addWidget(preset_grid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)

        # 10-band sliders
        bands_lbl = QLabel("Manual EQ  (−20 dB … +20 dB)")
        bands_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bands_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 7pt; background: transparent;")
        layout.addWidget(bands_lbl)

        bands_widget = QWidget()
        bands_widget.setStyleSheet(f"background: {SURFACE};")
        bands_layout = QHBoxLayout(bands_widget)
        bands_layout.setContentsMargins(0, 0, 0, 0)
        bands_layout.setSpacing(2)
        current_bands = self.player.equalizer.get_bands()
        band_sliders: list[QSlider]  = []
        val_labels:   list[QLabel]   = []
        _syncing = [False]

        for i, label in enumerate(Equalizer.BAND_LABELS):
            col_w = QWidget()
            col_w.setStyleSheet(f"background: {SURFACE};")
            col_l = QVBoxLayout(col_w)
            col_l.setContentsMargins(2, 0, 2, 0)
            col_l.setSpacing(2)
            col_l.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            val_lbl = QLabel(f"{current_bands[i]:+.0f}")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(
                f"color: {ACCENT}; background: transparent; font-size: 6pt;")
            col_l.addWidget(val_lbl)
            val_labels.append(val_lbl)

            sl = QSlider(Qt.Orientation.Vertical)
            sl.setRange(-20, 20)
            sl.setValue(int(current_bands[i]))
            sl.setFixedHeight(80)
            # FIX v11: positive groove margins instead of negative handle margins —
            # Qt 6 Windows rejects margin-left/margin-right with negative values on
            # vertical slider handles ("Could not parse stylesheet" × 2 per slider).
            sl.setStyleSheet(
                f"QSlider::groove:vertical {{ background: {SURFACE2}; width: 4px; border: none; "
                "margin-left: 3px; margin-right: 3px; }} "
                f"QSlider::handle:vertical {{ background: {ACCENT}; width: 10px; height: 10px; "
                "border: none; border-radius: 5px; }}"
            )
            _i = i
            def _on_band(val, bi=_i, vl=val_lbl):
                if _syncing[0]:
                    return
                self.player.set_eq_band(bi, float(val))
                vl.setText(f"{val:+d}")
                if not enable_cb.isChecked():
                    enable_cb.setChecked(True)
                    self.player.toggle_equalizer(True)
                _refresh_presets()
            sl.valueChanged.connect(_on_band)
            col_l.addWidget(sl)
            band_sliders.append(sl)

            freq_lbl = QLabel(label)
            freq_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            freq_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 6pt;")
            freq_lbl.setFixedWidth(30)
            freq_lbl.setWordWrap(True)
            col_l.addWidget(freq_lbl)
            bands_layout.addWidget(col_w)

        layout.addWidget(bands_widget)

        def _sync_sliders():
            _syncing[0] = True
            try:
                bands = self.player.equalizer.get_bands()
                for i, (sl, vl) in enumerate(zip(band_sliders, val_labels)):
                    sl.setValue(int(bands[i]))
                    vl.setText(f"{bands[i]:+.0f}")
            finally:
                _syncing[0] = False

        def _toggle_eq(checked: bool):
            self.player.toggle_equalizer(checked)
            _refresh_presets()

        enable_cb.toggled.connect(_toggle_eq)

        def _reset():
            self.player.equalizer.reset()
            _sync_sliders()
            _refresh_presets()

        reset_btn = QPushButton("Reset Flat")
        reset_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
            "font-size: 8pt; padding: 3px 10px;")
        reset_btn.clicked.connect(_reset)
        layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()

    # ── Sleep Timer ───────────────────────────────────────────────────────────

    def _open_sleep_dialog(self):
        if self._sleep_end is not None:
            self._cancel_sleep_timer()
            self._sleep_btn.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 13pt; padding: 0 8px;")
            self.toast("Sleep timer cancelled")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Sleep Timer")
        dlg.setFixedSize(270, 175)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title = QLabel("⏱  Sleep Timer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 11pt; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        minutes_slider = QSlider(Qt.Orientation.Horizontal)
        minutes_slider.setRange(5, 120)
        minutes_slider.setValue(30)
        # FIX v11: positive groove margins (no negative handle margins → no Qt 6 warnings)
        minutes_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {SURFACE2}; height: 6px; border: none; "
            "margin-top: 4px; margin-bottom: 4px; }} "
            f"QSlider::handle:horizontal {{ background: {ORANGE}; width: 14px; height: 14px; "
            "border: none; border-radius: 7px; }}"
        )

        minutes_lbl = QLabel("30 minutes")
        minutes_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        minutes_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 9pt; background: transparent;")
        minutes_slider.valueChanged.connect(
            lambda v: minutes_lbl.setText(f"{v} minutes"))
        layout.addWidget(minutes_slider)
        layout.addWidget(minutes_lbl)

        btn_row = QHBoxLayout()
        set_btn = QPushButton("Set Timer")
        set_btn.setStyleSheet(
            f"background: {ORANGE}; color: white; border: none; border-radius: 4px;"
            "font-size: 9pt; font-weight: bold; padding: 5px 14px;")

        def _set():
            mins = minutes_slider.value()
            self._start_sleep_timer(mins)
            self._sleep_btn.setStyleSheet(
                f"color: {ORANGE}; background: transparent; font-size: 13pt; padding: 0 8px;")
            self.toast(f"⏱  Sleep in {mins} min", kind="warning")
            dlg.accept()

        set_btn.clicked.connect(_set)
        btn_row.addWidget(set_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
            "font-size: 9pt; padding: 5px 10px;")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def _start_sleep_timer(self, minutes: int):
        self._cancel_sleep_timer()
        delay = minutes * 60
        self._sleep_end   = time.time() + delay
        self._sleep_thread = threading.Timer(delay, self._sleep_stop)
        self._sleep_thread.daemon = True
        self._sleep_thread.start()

    def _cancel_sleep_timer(self):
        if self._sleep_thread:
            self._sleep_thread.cancel()
            self._sleep_thread = None
        self._sleep_end = None

    def _sleep_stop(self):
        self._sleep_end    = None
        self._sleep_thread = None
        def _ui():
            self._stop()
            self._sleep_btn.setStyleSheet(
                f"color: {TEXT_DIM}; background: transparent; font-size: 13pt; padding: 0 8px;")
            self.toast("Sleep timer fired", kind="info")
        invoke_main(_ui)

    # ── Add Custom Station ─────────────────────────────────────────────────────

    def _open_add_station_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Custom Station")
        dlg.setFixedSize(390, 220)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title = QLabel("＋  Add Custom Station")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 11pt; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        def _field(label_txt: str) -> QLineEdit:
            row = QHBoxLayout()
            lbl = QLabel(label_txt)
            lbl.setFixedWidth(90)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt; background: transparent;")
            row.addWidget(lbl)
            entry = QLineEdit()
            entry.setStyleSheet(
                f"background: {SURFACE2}; color: {TEXT}; border: none; border-radius: 3px;"
                "font-size: 9pt; padding: 5px 8px;")
            row.addWidget(entry)
            layout.addLayout(row)
            return entry

        name_entry = _field("Name:")
        url_entry  = _field("Stream URL:")
        name_entry.setFocus()

        status_lbl = QLabel("")
        status_lbl.setStyleSheet(f"color: {RED}; background: transparent; font-size: 8pt;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_lbl)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("▶  Play & Add to Favorites")
        add_btn.setStyleSheet(
            f"background: {ACCENT}; color: black; border: none; border-radius: 4px;"
            "font-size: 9pt; font-weight: bold; padding: 5px 14px;")

        def _add():
            from core.api import is_safe_url
            name = name_entry.text().strip() or "Custom Station"
            url  = url_entry.text().strip()
            if not url:
                status_lbl.setText("Stream URL is required.")
                return
            if not is_safe_url(url):
                status_lbl.setText("Invalid URL (must be http:// or https://)")
                return
            station = {
                "name": name, "url": url, "logo": "",
                "country": "Custom", "tags": "custom",
                "bitrate": 0, "votes": 0, "codec": "", "language": "",
            }
            if url not in self._fav_urls:
                self.favorites.append(station)
                self._fav_urls.add(url)
                save_favorites(self.favorites)
            dlg.accept()
            self._play(station)
            self.toast(f"▶  Playing {name}", kind="success")

        add_btn.clicked.connect(_add)
        btn_row.addWidget(add_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
            "font-size: 9pt; padding: 5px 10px;")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _card_context_menu(self, event, station: dict):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; "
            f"font-size: 9pt; padding: 4px; border-radius: 6px; }} "
            f"QMenu::item {{ padding: 6px 20px; border-radius: 4px; margin: 1px 4px; }} "
            f"QMenu::item:selected {{ background: {ACCENT}; color: black; }} "
            f"QMenu::separator {{ height: 1px; background: {BORDER}; margin: 3px 6px; }}"
        )
        menu.addAction("▶  Play",      lambda: self._play(station))
        menu.addSeparator()
        menu.addAction("📋  Copy Stream URL",
                       lambda: self._copy_to_clip(station["url"]))
        menu.addAction("📋  Copy Station Name",
                       lambda: self._copy_to_clip(station.get("name", "")))
        menu.addSeparator()
        url = station["url"]
        if url in self._fav_urls:
            menu.addAction("💔  Remove from Favorites",
                           lambda: self._fav_from_menu(station, remove=True))
        else:
            menu.addAction("❤  Add to Favorites",
                           lambda: self._fav_from_menu(station, remove=False))
        menu.addSeparator()
        menu.addAction("ℹ  Station Info",
                       lambda: self._show_station_info(station))
        if STATS_ENABLED:
            pc = play_stats.get_play_count(url)
            ts = play_stats.get_total_seconds(url) if pc else 0
            if pc:
                menu.addSeparator()
                info_act = menu.addAction(
                    f"▶ Played {pc}×  ·  {_fmt_time(ts)} total")
                info_act.setEnabled(False)
        menu.exec(event.globalPos())

    def _copy_to_clip(self, text: str):
        QApplication.clipboard().setText(text)
        self.toast("Copied to clipboard")

    def _fav_from_menu(self, station: dict, remove: bool):
        url = station["url"]
        if remove and url in self._fav_urls:
            self.favorites  = [f for f in self.favorites if f["url"] != url]
            self._fav_urls.discard(url)
            self.toast("Removed from Favorites")
        elif not remove and url not in self._fav_urls:
            self.favorites.append(station)
            self._fav_urls.add(url)
            self.toast("❤  Added to Favorites", kind="success")
        save_favorites(self.favorites)
        self._render_grid()

    # ── Station Info dialog ───────────────────────────────────────────────────

    def _show_station_info(self, station: dict):
        dlg = QDialog(self)
        dlg.setWindowTitle("Station Info")
        dlg.setFixedSize(400, 380)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        title = QLabel("ℹ  Station Info")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 11pt; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)

        meta_text = ""
        if self.current_station and self.current_station.get("url") == station.get("url"):
            meta = self.player.get_current_metadata()
            if meta.get("title"):
                meta_text = meta["title"]

        votes_val = station.get("votes", 0)
        votes_str = f"{votes_val:,}" if votes_val else "—"
        lang      = (station.get("language") or "").strip()

        fields = [
            ("Name",     _clean_name(station.get("name", ""))),
            ("Country",  station.get("country", "") or "—"),
            ("Language", lang or "—"),
            ("Tags",     (station.get("tags", "") or "—")[:60]),
            ("Bitrate",  f"{station.get('bitrate', 0)} kbps" if station.get("bitrate") else "—"),
            ("Codec",    station.get("codec", "") or "—"),
            ("Votes",    votes_str),
            ("URL",      (station.get("url", "")[:55] + "…"
                          if len(station.get("url", "")) > 55 else station.get("url", ""))),
        ]
        if meta_text:
            fields.insert(0, ("Now Playing", meta_text[:55]))
        if STATS_ENABLED:
            url = station.get("url", "")
            pc  = play_stats.get_play_count(url)
            ts  = play_stats.get_total_seconds(url) if pc else 0
            if pc:
                fields.append(("Played", f"{pc}×  ·  {_fmt_time(ts)} total"))

        for label, value in fields:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(90)
            lbl.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 8pt; font-weight: bold; background: transparent;")
            row.addWidget(lbl)
            val = QLabel(value or "—")
            val.setStyleSheet(
                f"color: {TEXT}; font-size: 8pt; background: transparent;")
            val.setWordWrap(True)
            row.addWidget(val, stretch=1)
            layout.addLayout(row)

        layout.addStretch()

        btn_row = QHBoxLayout()
        play_btn = QPushButton("▶  Play")
        play_btn.setStyleSheet(
            f"background: {ACCENT}; color: black; border: none; border-radius: 4px;"
            "font-size: 9pt; font-weight: bold; padding: 4px 12px;")
        play_btn.clicked.connect(lambda: [dlg.accept(), self._play(station)])
        btn_row.addWidget(play_btn)

        copy_btn = QPushButton("📋 Copy URL")
        copy_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
            "font-size: 9pt; padding: 4px 10px;")
        copy_btn.clicked.connect(lambda: self._copy_to_clip(station["url"]))
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
            "font-size: 9pt; padding: 4px 10px;")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    # ── Help dialog ───────────────────────────────────────────────────────────

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Help & Shortcuts")
        dlg.setFixedSize(440, 620)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        title = QLabel("⌨  Keyboard Shortcuts & Info")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 11pt; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)

        shortcuts = [
            ("Space",        "Stop / Resume last station"),
            ("M",            "Toggle mute"),
            ("F",            "Toggle favourite (current station)"),
            ("T",            "Toggle always-on-top pin"),
            ("R",            "Refresh current category"),
            ("N",            "Play random station"),
            ("← / →",        "Previous / Next station"),
            ("↑ / ↓",        f"Volume +/− {VOLUME_STEP}%"),
            ("Scroll wheel", f"Volume +/− {VOLUME_STEP}% (header/now-bar)"),
            ("Ctrl+F",       "Focus search bar"),
            ("Ctrl+M",       "Toggle mini player"),
            ("Ctrl+U",       "Add custom stream URL"),
            ("Escape",       "Cancel auto-resume / clear search"),
            ("?",            "Show this help"),
            ("",             ""),
            ("Right-click",  "Station context menu"),
            ("Double-click", "Station info popup"),
            ("EQ button",    "Equalizer + 10-band sliders"),
            ("⏱ button",    "Sleep timer (5–120 min)"),
            ("＋ button",    "Add custom radio station"),
            ("⧉ button",    "Toggle mini player"),
        ]

        # ── Scrollable shortcuts list ─────────────────────────────────────────
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {SURFACE}; }}"
            f"QScrollBar:vertical {{ background: {SURFACE2}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 3px; }}"
        )

        sc_widget = QWidget()
        sc_widget.setStyleSheet(f"background: {SURFACE};")
        sc_layout = QVBoxLayout(sc_widget)
        sc_layout.setContentsMargins(0, 0, 6, 0)
        sc_layout.setSpacing(3)

        for key, desc in shortcuts:
            if not key:
                s2 = QFrame()
                s2.setFrameShape(QFrame.Shape.HLine)
                s2.setStyleSheet(f"color: {BORDER};")
                sc_layout.addWidget(s2)
                continue
            row = QHBoxLayout()
            row.setContentsMargins(0, 1, 0, 1)
            k = QLabel(key)
            k.setFixedWidth(110)
            k.setStyleSheet(
                f"color: {ACCENT}; font-size: 9pt; font-weight: bold; background: transparent;")
            row.addWidget(k)
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9pt; background: transparent;")
            row.addWidget(d, stretch=1)
            sc_layout.addLayout(row)

        # Stats inside scroll area
        s = db_stats()
        mb = s["total_bytes"] / (1024 * 1024)
        cache_lbl = QLabel(f"Logo cache: {s['count']} logos  ({mb:.1f} MB)")
        cache_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cache_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 8pt; background: transparent; padding-top: 6px;")
        sc_layout.addWidget(cache_lbl)

        if STATS_ENABLED:
            today = play_stats.get_today_listen_time()
            total = play_stats.get_total_listen_time()
            time_lbl = QLabel(
                f"Listening: {_fmt_time(today)} this session  ·  {_fmt_time(total)} all-time")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            time_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 8pt; background: transparent;")
            sc_layout.addWidget(time_lbl)

        sc_layout.addStretch()
        scroll.setWidget(sc_widget)
        layout.addWidget(scroll, stretch=1)

        # Bottom action buttons — each in its own row so they never overflow
        layout.addSpacing(6)
        for label, cb in [
            ("Export Favorites (JSON)", self._export_favorites),
            ("Export M3U",             self._export_m3u),
            ("Import Favorites",       self._import_favorites),
        ]:
            b = QPushButton(label)
            b.setStyleSheet(
                f"background: {SURFACE2}; color: {TEXT_DIM}; border: none; border-radius: 4px;"
                "font-size: 9pt; padding: 5px 10px;")
            b.clicked.connect(cb)
            layout.addWidget(b)

        layout.addSpacing(4)
        close_btn = QPushButton("✕  Close")
        close_btn.setStyleSheet(
            f"background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER2};"
            "border-radius: 4px; font-size: 9pt; font-weight: bold; padding: 5px 14px;")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()
