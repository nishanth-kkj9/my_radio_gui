"""
ui/spectrum.py — Professional spectrum analyzer widget (PyQt6) — v12.

Changes vs v11:
  • Increased bar dimensions: BAR_W 5→7, GAP 3→4, BAR_H 38→58, REF_H 14→22
  • Canvas is now 174×80 px (was 127×52) — roughly 37% wider and 54% taller.
  • _FREQ max_amp values scaled proportionally to fill the larger BAR_H.
  • All animation logic and color LUTs are unchanged.
"""
from __future__ import annotations

import random

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter, QColor

from core.theme import SURFACE2, NOW_BAR

# ── Geometry ──────────────────────────────────────────────────────────────────
N_BARS   = 16
BAR_W    = 7            # was 5
GAP      = 4            # was 3
MARGIN_L = 2
BAR_STEP = BAR_W + GAP                          # 11 px per bar
CANVAS_W = MARGIN_L + N_BARS * BAR_STEP - GAP  # 174 px (was 127)
BAR_H    = 58           # was 38  (+53%)
REF_H    = 22           # was 14
CANVAS_H = BAR_H + REF_H                        # 80 px (was 52)

# ── Animation timing ──────────────────────────────────────────────────────────
TICK_MS    = 55         # slightly faster for smoother animation
PEAK_HOLD  = 16
PEAK_FALL  = 0.8
IDLE_DRAIN = 0.9

# ── Frequency characteristics per bar ─────────────────────────────────────────
# max_amp values scaled by 58/38 ≈ 1.526 from original to fill the taller BAR_H
_FREQ = [
    (0.10, 58, 0.16), (0.12, 57, 0.18),
    (0.15, 54, 0.21), (0.17, 52, 0.24),
    (0.21, 49, 0.28), (0.25, 46, 0.32),
    (0.28, 43, 0.36), (0.31, 40, 0.39),
    (0.36, 37, 0.43), (0.40, 32, 0.47),
    (0.43, 28, 0.51), (0.46, 25, 0.54),
    (0.51, 21, 0.60), (0.56, 17, 0.65),
    (0.60, 14, 0.70), (0.65, 11, 0.75),
]

# ── Beat simulation ───────────────────────────────────────────────────────────
BEAT_BOOST      = 0.88
BEAT_HOLD       = 3
MIN_BEAT_FRAMES = 6
MAX_BEAT_FRAMES = 28


def _build_color_lut(steps: int = 256) -> tuple[list[str], list[str], list[str]]:
    """Pre-calculate bar, reflect, and peak colors for ratio 0.0→1.0."""
    bars, reflects, peaks = [], [], []
    for i in range(steps):
        ratio = i / (steps - 1)
        if ratio < 0.55:
            t = ratio / 0.55
            r = int(0x03 + t * (0x00 - 0x03))
            g = int(0x28 + t * (0xd4 - 0x28))
            b = int(0x50 + t * (0xff - 0x50))
        else:
            t = (ratio - 0.55) / 0.45
            r = int(0x00 + t * (0x7c - 0x00))
            g = int(0xd4 + t * (0x5c - 0xd4))
            b = int(0xff + t * (0xfc - 0xff))
        bars.append(f"#{r:02x}{g:02x}{b:02x}")
        reflects.append(f"#{int(r*0.22):02x}{int(g*0.22):02x}{int(b*0.22):02x}")
        intensity = 0.55 + ratio * 0.45
        peaks.append(
            f"#{int(0xc0 * intensity):02x}"
            f"{int(0xe8 * intensity):02x}"
            f"{int(0xff * intensity):02x}"
        )
    return bars, reflects, peaks


_LUT_STEPS = 256
_BAR_LUT, _REFLECT_LUT, _PEAK_LUT = _build_color_lut(_LUT_STEPS)


def _lut_index(ratio: float) -> int:
    return max(0, min(_LUT_STEPS - 1, int(ratio * (_LUT_STEPS - 1))))


class SpectrumWidget(QWidget):
    """
    Drop-in QWidget that draws an animated spectrum analyzer via QPainter.
    Dimensions: 174 × 80 px (enlarged in v12).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(CANVAS_W, CANVAS_H)

        self._active   = False
        self._heights  = [float(random.randint(2, 6)) for _ in range(N_BARS)]
        self._targets  = [float(random.randint(2, h)) for _, h, _ in _FREQ]
        self._peaks    = [0.0] * N_BARS
        self._pk_hold  = [0]   * N_BARS

        self._beat_down = random.randint(MIN_BEAT_FRAMES, MAX_BEAT_FRAMES)
        self._beat_hold = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

        self._bg_color       = QColor(NOW_BAR)
        self._surface2_color = QColor(SURFACE2)
        self._mirror_color   = QColor("#1a2a3a")
        self._bar_colors     = [QColor(c) for c in _BAR_LUT]
        self._reflect_colors = [QColor(c) for c in _REFLECT_LUT]
        self._peak_colors    = [QColor(c) for c in _PEAK_LUT]

    # ── Public controls ───────────────────────────────────────────────────────

    def start(self):
        if self._active:
            return
        self._active = True
        if not self._timer.isActive():
            self._timer.start(TICK_MS)

    def stop(self):
        self._active = False

    # ── Animation loop ────────────────────────────────────────────────────────

    def _animate(self):
        if self._active:
            self._update_active()
        else:
            self._update_idle()
            if not any(h > 1.5 for h in self._heights):
                self.update()
                self._timer.stop()
                return
        self.update()

    def _update_active(self):
        if self._beat_hold > 0:
            self._beat_hold -= 1
        else:
            self._beat_down -= 1
            if self._beat_down <= 0:
                for i, (_, max_amp, _) in enumerate(_FREQ):
                    self._targets[i] = max_amp * BEAT_BOOST
                self._beat_hold = BEAT_HOLD
                self._beat_down = random.randint(MIN_BEAT_FRAMES, MAX_BEAT_FRAMES)

        for i, (prob, max_amp, speed) in enumerate(_FREQ):
            if self._beat_hold <= 0 and random.random() < prob:
                self._targets[i] = random.gauss(max_amp * 0.55, max_amp * 0.28)
                self._targets[i] = max(2.0, min(float(max_amp), self._targets[i]))
            cur  = self._heights[i]
            tgt  = self._targets[i]
            diff = tgt - cur
            step = max(0.8, abs(diff) * speed)
            cur  = min(cur + step, tgt) if diff > 0 else max(cur - step, tgt)
            self._heights[i] = cur
            if cur >= self._peaks[i]:
                self._peaks[i]   = cur
                self._pk_hold[i] = PEAK_HOLD
            elif self._pk_hold[i] > 0:
                self._pk_hold[i] -= 1
            else:
                self._peaks[i] = max(0.0, self._peaks[i] - PEAK_FALL)

    def _update_idle(self):
        for i in range(N_BARS):
            self._heights[i] *= IDLE_DRAIN
            if self._heights[i] < 1.0:
                self._heights[i] = 0.0
            self._targets[i] = self._heights[i]
            self._peaks[i]   = max(0.0, self._peaks[i] - PEAK_FALL * 2)
            self._pk_hold[i] = 0

    # ── Drawing ───────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        p.fillRect(self.rect(), self._bg_color)

        p.setPen(self._mirror_color)
        p.drawLine(0, BAR_H, CANVAS_W, BAR_H)

        for i in range(N_BARS):
            h  = max(0.0, self._heights[i])
            pk = max(0.0, self._peaks[i])
            x1 = MARGIN_L + i * BAR_STEP
            ratio = h / BAR_H if BAR_H > 0 else 0.0
            idx   = _lut_index(ratio)

            if h > 0.5:
                p.fillRect(x1, int(BAR_H - h), BAR_W, max(1, int(h)),
                           self._bar_colors[idx])
            else:
                p.fillRect(x1, BAR_H - 2, BAR_W, 2, self._surface2_color)

            if h > 0.5:
                ref_h = max(1, int(h * 0.30))
                p.fillRect(x1, BAR_H, BAR_W, ref_h,
                           self._reflect_colors[idx])

            if pk > 3.0:
                pk_idx = _lut_index(pk / BAR_H if BAR_H > 0 else 0)
                pk_top = max(0, int(BAR_H - pk - 1))
                p.fillRect(x1, pk_top, BAR_W, 2,
                           self._peak_colors[pk_idx])

        p.end()
