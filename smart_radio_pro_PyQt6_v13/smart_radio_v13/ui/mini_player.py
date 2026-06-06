"""
ui/mini_player.py — Compact always-on-top mini player (PyQt6) — v12.

Changes vs v11:
  • Layout redesigned: Logo | Name+ICY | [Mute] [Next] [Vol icon + Slider] [Expand]
  • Stop and Random buttons removed; replaced with Mute and Next (within category).
  • Next button navigates to next station within the current category only.
  • All buttons separated by explicit spacings — zero overlap guaranteed.
  • Volume slider upgraded: sub-page fill shows current level; smooth
    QPropertyAnimation easing when the value is updated externally.
  • Pin button completely removed.
  • Width widened to 560 px so every control has breathing room.
  • Mute icon updates reactively every refresh cycle.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QLabel, QSlider,
    QHBoxLayout, QVBoxLayout, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QCursor, QFontMetrics

from core.theme import ACCENT, ACCENT2, BORDER, NOW_BAR, SURFACE2, TEXT, TEXT_DIM

MINI_W  = 560   # wide enough for all controls with generous spacing
MINI_H  = 86
LOGO_SZ = 48


class MiniPlayer(QWidget):
    """
    Compact always-on-top player panel.

    Callbacks injected at construction time (all keyword-only):
        on_expand        — called when the expand button is clicked
        on_mute          — called when the mute/unmute button is clicked
        on_next          — called when the next-station button is clicked
        on_volume_change — called with (int) when the volume slider moves
        get_volume       — () -> int   current player volume 0-100
        get_station_name — () -> str   currently playing station name
        get_icy_text     — () -> str   ICY now-playing metadata text
        get_logo_pixmap  — () -> QPixmap | None   current station logo
        default_logo_pixmap — QPixmap  fallback logo
        is_playing       — () -> bool  is audio currently playing
        is_muted         — () -> bool  is audio currently muted
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        on_expand,
        on_mute,
        on_next,
        on_volume_change,
        get_volume,
        get_station_name,
        get_icy_text,
        get_logo_pixmap,
        default_logo_pixmap,
        is_playing,
        is_muted,
    ):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._cb_expand  = on_expand
        self._cb_mute    = on_mute
        self._cb_next    = on_next
        self._cb_vol     = on_volume_change
        self._get_vol    = get_volume
        self._get_name   = get_station_name
        self._get_icy    = get_icy_text
        self._get_logo   = get_logo_pixmap
        self._def_logo   = default_logo_pixmap
        self._is_playing = is_playing
        self._is_muted   = is_muted

        self.setFixedSize(MINI_W, MINI_H)
        self.setStyleSheet(f"background: {NOW_BAR};")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Default position: centre-bottom of primary screen
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - MINI_W) // 2, screen.height() - MINI_H - 60)

        self._drag_pos: QPoint | None = None
        self._vol_anim: QPropertyAnimation | None = None

        self._build()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top accent bar
        bar = QFrame()
        bar.setFixedHeight(3)
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet(f"background: {ACCENT};")
        root.addWidget(bar)

        # Body row
        body = QWidget()
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body.setStyleSheet(f"background: {NOW_BAR};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(12, 4, 18, 4)
        body_layout.setSpacing(0)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Logo
        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedSize(LOGO_SZ, LOGO_SZ)
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_lbl.setStyleSheet(f"background: {NOW_BAR};")
        if self._def_logo:
            self._logo_lbl.setPixmap(self._def_logo)
        body_layout.addWidget(self._logo_lbl)
        body_layout.addSpacing(10)

        # Station info (name + ICY) — stretches to fill remaining space
        info = QWidget()
        info.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        info.setStyleSheet(f"background: {NOW_BAR};")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._name_lbl = QLabel("Nothing playing")
        self._name_lbl.setStyleSheet(
            f"color: {TEXT}; background: transparent; "
            "font-weight: bold; font-size: 10pt; letter-spacing: 0.2px;")
        info_layout.addWidget(self._name_lbl)

        self._icy_lbl = QLabel("")
        self._icy_lbl.setStyleSheet(
            f"color: {ACCENT2}; background: transparent; font-size: 8pt;")
        info_layout.addWidget(self._icy_lbl)

        body_layout.addWidget(info, stretch=1)
        body_layout.addSpacing(10)

        # Controls helper
        def _icon_btn(text: str, cb, size: int = 12,
                      tip: str = "", fixed_w: int = 32) -> QLabel:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(fixed_w, 28)
            _base  = (f"color: {TEXT_DIM}; background: transparent; "
                      f"font-size: {size}pt;")
            _hover = (f"color: {ACCENT}; background: transparent; "
                      f"font-size: {size}pt;")
            lbl.setStyleSheet(_base)
            lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            lbl.mousePressEvent = lambda _e: cb()
            lbl.enterEvent      = lambda _e: lbl.setStyleSheet(_hover)
            lbl.leaveEvent      = lambda _e: lbl.setStyleSheet(_base)
            if tip:
                lbl.setToolTip(tip)
            return lbl

        # Mute / unmute button
        muted_now = self._is_muted()
        self._mute_btn = _icon_btn(
            "🔇" if muted_now else "🔊",
            self._on_mute_click,
            size=11, tip="Mute / Unmute  (M)", fixed_w=32,
        )
        body_layout.addWidget(self._mute_btn)
        body_layout.addSpacing(10)

        # Next-station button (within current category)
        next_btn = _icon_btn(
            "⏭", self._cb_next,
            size=12, tip="Next station  (Right Arrow)", fixed_w=32,
        )
        body_layout.addWidget(next_btn)
        body_layout.addSpacing(10)

        # Volume icon (visual cue, non-interactive)
        vol_icon = QLabel("🔉")
        vol_icon.setFixedWidth(16)
        vol_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_icon.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; font-size: 8pt;")
        body_layout.addWidget(vol_icon)
        body_layout.addSpacing(4)

        # Volume slider with sub-page fill for visual level indication
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(self._get_vol())
        self._vol_slider.setFixedWidth(90)
        self._vol_slider.setFixedHeight(24)
        self._vol_slider.setToolTip("Volume")
        # Qt6/Windows-safe QSS: no border-radius on groove/sub-page,
        # positive groove margins only (negative handle margins cause parse errors)
        self._vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {SURFACE2}; height: 4px;"
            "  border: none; margin: 10px 0; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT}; height: 4px;"
            "  border: none; margin: 10px 0; }}"
            f"QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; height: 14px;"
            "  border: none; border-radius: 7px; margin: -5px 0; }}"
        )
        self._vol_slider.valueChanged.connect(self._cb_vol)
        body_layout.addWidget(self._vol_slider)
        body_layout.addSpacing(14)

        # Expand / maximise button — always visible, fixed width
        expand_btn = _icon_btn(
            "⤢", self._cb_expand,
            size=11, tip="Expand to full window  (Ctrl+M)", fixed_w=30,
        )
        body_layout.addWidget(expand_btn)

        root.addWidget(body)

        # Bottom border
        bot = QFrame()
        bot.setFixedHeight(1)
        bot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bot.setStyleSheet(f"background: {BORDER};")
        root.addWidget(bot)

    # ── Mute click ────────────────────────────────────────────────────────────

    def _on_mute_click(self):
        self._cb_mute()
        # Immediate icon update; _refresh() will also correct it on next cycle
        muted = self._is_muted()
        self._mute_btn.setText("🔇" if muted else "🔊")

    # ── Smooth volume animation ────────────────────────────────────────────────

    def _smooth_vol_to(self, target: int):
        """Animate the volume slider to *target* with easing."""
        if self._vol_anim:
            self._vol_anim.stop()
        self._vol_anim = QPropertyAnimation(self._vol_slider, b"value")
        self._vol_anim.setDuration(140)
        self._vol_anim.setStartValue(self._vol_slider.value())
        self._vol_anim.setEndValue(target)
        self._vol_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._vol_anim.start()

    # ── Periodic refresh ──────────────────────────────────────────────────────

    def _refresh(self):
        try:
            name = self._get_name() or "Nothing playing"
            icy  = self._get_icy()  or ""

            fm      = QFontMetrics(self._name_lbl.font())
            avail_w = max(self._name_lbl.width() - 6, 80)
            elided  = fm.elidedText(name, Qt.TextElideMode.ElideRight, avail_w)
            self._name_lbl.setText(elided)
            self._icy_lbl.setText(icy[:44] + "…" if len(icy) > 44 else icy)

            logo = self._get_logo()
            if logo and not logo.isNull():
                self._logo_lbl.setPixmap(logo.scaled(
                    LOGO_SZ, LOGO_SZ,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            elif self._def_logo:
                self._logo_lbl.setPixmap(self._def_logo)

            # Sync volume — animate smoothly when out of sync
            cur_vol = self._get_vol()
            if abs(self._vol_slider.value() - cur_vol) > 1:
                self._vol_slider.blockSignals(True)
                self._smooth_vol_to(cur_vol)
                self._vol_slider.blockSignals(False)

            # Sync mute icon
            muted = self._is_muted()
            expected = "🔇" if muted else "🔊"
            if self._mute_btn.text() != expected:
                self._mute_btn.setText(expected)

        except Exception:
            pass

    # ── Drag to reposition ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Public lifecycle ──────────────────────────────────────────────────────

    def cleanup(self):
        """Stop all timers and animations before the widget is destroyed."""
        self._timer.stop()
        if self._vol_anim:
            self._vol_anim.stop()
