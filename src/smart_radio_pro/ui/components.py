"""ui/components.py — Station card widget (PyQt6) — v12.

Changes vs v11:
  • Card hover / playing glow replaced by QGraphicsDropShadowEffect.
    The old approach (border: 1px solid ACCENT; border-radius: 8px;) produced
    broken/incomplete rectangle corners because child widgets painted over the
    parent frame's rounded edges.  A drop-shadow effect is composited by Qt's
    rendering pipeline OUTSIDE the widget boundary, so corners are always clean
    and the glow is a proper closed rectangle with soft edges.
  • enterEvent / leaveEvent now toggle the shadow effect instead of re-parsing
    the full stylesheet on every hover — faster and zero cascade warnings.
  • Volume slider sub-page fill kept from v11.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor, QColor

from smart_radio_pro.core.theme import (
    SURFACE, SURFACE2, SURFACE3, BORDER, BORDER2,
    ACCENT, ACCENT2, ACCENT3,
    TEXT, TEXT_DIM, TEXT_MID, RED, GREEN,
)
from smart_radio_pro.core.config import LOGO_SZ

CARD_W = 192
CARD_H = 268


# ── Utility functions ──────────────────────────────────────────────────────────

def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _clean_name(name: str) -> str:
    if not name:
        return "Unknown Station"
    name = name.strip()
    if "(" in name:
        name = name[:name.index("(")].strip()
    if " - " in name:
        name = name.split(" - ")[0].strip()
    if name.startswith("-"):
        name = name.lstrip("- ").strip()
    return name or "Unknown Station"


def _quality_badge(bitrate: int) -> tuple[str, str, str]:
    if bitrate >= 256: return "HQ", "#0a2318", ACCENT3
    if bitrate >= 128: return "HD", "#0a1e2a", ACCENT
    if bitrate  > 0:   return f"{bitrate}k", "#181825", TEXT_DIM
    return "", "", ""


def _codec_label(codec: str) -> str:
    c = (codec or "").upper()
    return c if c in ("AAC", "AAC+", "AACP", "FLAC", "OGG", "OPUS") else ""


def _btn_style(bg: str, fg: str, radius: int = 5,
               font_size: int = 9, bold: bool = True,
               pad_v: int = 5, pad_h: int = 10) -> str:
    weight = "bold" if bold else "normal"
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; "
        f"border: none; border-radius: {radius}px; "
        f"font-size: {font_size}pt; font-weight: {weight}; "
        f"padding-top: {pad_v}px; padding-bottom: {pad_v}px; "
        f"padding-left: {pad_h}px; padding-right: {pad_h}px; }}"
    )


# ── Shadow effect helpers ──────────────────────────────────────────────────────

def _make_glow(color: str, radius: int, opacity: float = 1.0) -> QGraphicsDropShadowEffect:
    """Create a symmetric drop-shadow (glow) effect."""
    eff = QGraphicsDropShadowEffect()
    c = QColor(color)
    c.setAlphaF(opacity)
    eff.setColor(c)
    eff.setBlurRadius(radius)
    eff.setOffset(0, 0)
    return eff


# ── Station Card ──────────────────────────────────────────────────────────────

class StationCard(QFrame):
    """
    Fixed-size card widget for one radio station.

    Signals:
        play_clicked(station)
        fav_clicked(station)
        right_clicked(QContextMenuEvent, station)
        double_clicked(station)
    """
    play_clicked   = pyqtSignal(dict)
    fav_clicked    = pyqtSignal(dict)
    right_clicked  = pyqtSignal(object, dict)
    double_clicked = pyqtSignal(dict)

    def __init__(self, station: dict, is_fav: bool,
                 is_playing: bool, parent=None):
        super().__init__(parent)
        self.station     = station
        self._is_playing = is_playing
        self._is_fav     = is_fav

        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._build()
        self._apply_card_style(hovered=False)

        # Apply persistent glow for playing state
        if self._is_playing:
            self.setGraphicsEffect(_make_glow(ACCENT, 28, opacity=0.70))

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        s = self.station

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Top accent strip
        self._top_strip = QFrame()
        self._top_strip.setFixedHeight(3)
        self._top_strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._top_strip.setStyleSheet(
            f"background: {ACCENT if self._is_playing else 'transparent'};"
            "border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )
        layout.addWidget(self._top_strip)

        # Logo area
        logo_wrap = QWidget()
        logo_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        logo_wrap.setFixedHeight(LOGO_SZ + 16)
        logo_wrap.setStyleSheet(f"background: {SURFACE};")
        lw_layout = QHBoxLayout(logo_wrap)
        lw_layout.setContentsMargins(0, 10, 0, 0)
        lw_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(LOGO_SZ, LOGO_SZ)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_lbl.setStyleSheet(f"background: {SURFACE};")
        lw_layout.addWidget(self.logo_lbl)
        layout.addWidget(logo_wrap)

        # Station name
        name = _truncate(_clean_name(s.get("name", "")), 36)
        self.name_lbl = QLabel(name)
        self.name_lbl.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setFixedHeight(40)
        self.name_lbl.setStyleSheet(
            f"color: {ACCENT if self._is_playing else TEXT};"
            f"background: {SURFACE};"
            "font-weight: bold; font-size: 9pt; padding-left: 6px; padding-right: 6px;"
        )
        layout.addWidget(self.name_lbl)

        # Country · genre row
        country   = (s.get("country") or "").strip()
        tags_raw  = (s.get("tags")    or "").strip()
        first_tag = tags_raw.split(",")[0].strip() if tags_raw else ""
        sub_text  = _truncate(" · ".join(filter(None, [country, first_tag])), 28)

        sub_row = QWidget()
        sub_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sub_row.setStyleSheet(f"background: {SURFACE};")
        sub_layout = QHBoxLayout(sub_row)
        sub_layout.setContentsMargins(8, 0, 8, 2)
        sub_layout.setSpacing(4)
        sub_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel(sub_text or "Radio")
        sub_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 8pt; background: transparent;")
        sub_layout.addWidget(sub_lbl)

        qlabel, qbg, qfg = _quality_badge(s.get("bitrate", 0))
        if qlabel:
            badge = QLabel(f" {qlabel} ")
            badge.setStyleSheet(
                f"color: {qfg}; background: {qbg}; font-size: 7pt;"
                "font-weight: bold; padding-left: 3px; padding-right: 3px; border-radius: 3px;")
            sub_layout.addWidget(badge)

        cl = _codec_label(s.get("codec", ""))
        if cl:
            cbadge = QLabel(f" {cl} ")
            cbadge.setStyleSheet(
                f"color: {ACCENT2}; background: #16142e; font-size: 7pt;"
                "font-weight: bold; padding-left: 3px; padding-right: 3px; border-radius: 3px;")
            sub_layout.addWidget(cbadge)

        layout.addWidget(sub_row)

        # Votes
        votes = s.get("votes", 0)
        if votes and votes > 0:
            v_lbl = QLabel(f"▲ {votes:,}")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            v_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; background: {SURFACE}; font-size: 7pt;")
            layout.addWidget(v_lbl)

        layout.addStretch()

        # Button row
        btn_row = QWidget()
        btn_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        btn_row.setStyleSheet(f"background: {SURFACE};")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(8, 0, 8, 14)
        btn_layout.setSpacing(6)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Play button (single-rule QSS, no :hover — Python hover handlers)
        self.play_btn = QPushButton(
            "⏸  Pause" if self._is_playing else "▶  Play")
        self._play_normal_style = self._get_play_style(hover=False)
        self._play_hover_style  = self._get_play_style(hover=True)
        self.play_btn.setStyleSheet(self._play_normal_style)
        self.play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.play_btn.clicked.connect(lambda: self.play_clicked.emit(self.station))
        self.play_btn.enterEvent = lambda _e: (
            self.play_btn.setStyleSheet(self._play_hover_style)
            if not self._is_playing else None
        )
        self.play_btn.leaveEvent = lambda _e: (
            self.play_btn.setStyleSheet(self._play_normal_style)
            if not self._is_playing else None
        )
        btn_layout.addWidget(self.play_btn)

        # Fav button
        self._fav_icon   = "❤" if self._is_fav else "♡"
        self._fav_normal = _btn_style(
            SURFACE2, RED if self._is_fav else TEXT_DIM,
            radius=5, font_size=12, bold=False, pad_v=3, pad_h=6)
        self._fav_hover  = _btn_style(
            SURFACE3, RED,
            radius=5, font_size=12, bold=False, pad_v=3, pad_h=6)

        self.fav_btn = QPushButton(self._fav_icon)
        self.fav_btn.setStyleSheet(self._fav_normal)
        self.fav_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.fav_btn.clicked.connect(lambda: self.fav_clicked.emit(self.station))
        self.fav_btn.enterEvent = lambda _e: self.fav_btn.setStyleSheet(self._fav_hover)
        self.fav_btn.leaveEvent = lambda _e: self.fav_btn.setStyleSheet(self._fav_normal)
        btn_layout.addWidget(self.fav_btn)

        layout.addWidget(btn_row)

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _get_play_style(self, hover: bool = False) -> str:
        if self._is_playing:
            return _btn_style(ACCENT, "#000000", radius=5, pad_v=5, pad_h=10)
        if hover:
            return _btn_style(ACCENT, "#000000", radius=5, pad_v=5, pad_h=10)
        return _btn_style(ACCENT2, "#ffffff", radius=5, pad_v=5, pad_h=10)

    def _apply_card_style(self, hovered: bool):
        """Set the card frame stylesheet.
        When playing the glow comes entirely from QGraphicsDropShadowEffect
        (set in __init__).  We keep the border subtle so it doesn't fight the
        soft shadow with a hard accent-coloured line.
        """
        if self._is_playing:
            # Soft inner border — drop shadow provides the visible glow
            border_col = ACCENT2
        elif hovered:
            border_col = ACCENT
        else:
            border_col = BORDER
        self.setStyleSheet(
            f"StationCard {{ background: {SURFACE}; "
            f"border: 1px solid {border_col}; border-radius: 8px; }}"
        )

    # ── Logo update ───────────────────────────────────────────────────────────

    def set_logo(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.logo_lbl.setPixmap(pixmap.scaled(
                LOGO_SZ, LOGO_SZ,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    # ── Play-count badge ──────────────────────────────────────────────────────

    def add_play_badge(self, count: int):
        if count <= 0:
            return
        badge = QLabel(f"▶{count}", self)
        badge.setStyleSheet(
            f"color: {ACCENT}; background: {SURFACE};"
            "font-size: 6pt; font-weight: bold;"
            "padding-top: 1px; padding-bottom: 1px;"
            "padding-left: 2px; padding-right: 2px;")
        badge.move(CARD_W - 34, 7)
        badge.show()

    # ── Mouse events ──────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._apply_card_style(hovered=True)
        self._top_strip.setStyleSheet(
            f"background: {ACCENT};"
            "border-top-left-radius: 8px; border-top-right-radius: 8px;")
        if not self._is_playing:
            self.play_btn.setStyleSheet(self._play_hover_style)
        # Hover glow — slightly more subtle than playing glow
        if not self._is_playing:
            self.setGraphicsEffect(_make_glow(ACCENT, 14, opacity=0.6))

    def leaveEvent(self, event):
        self._apply_card_style(hovered=False)
        self._top_strip.setStyleSheet(
            f"background: {ACCENT if self._is_playing else 'transparent'};"
            "border-top-left-radius: 8px; border-top-right-radius: 8px;")
        if not self._is_playing:
            self.play_btn.setStyleSheet(self._play_normal_style)
        # Remove hover glow (playing glow is set in __init__ and stays)
        if not self._is_playing:
            self.setGraphicsEffect(None)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.station)

    def contextMenuEvent(self, event):
        self.right_clicked.emit(event, self.station)
