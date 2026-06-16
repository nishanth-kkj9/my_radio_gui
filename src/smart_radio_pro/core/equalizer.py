"""
core/equalizer.py — 10-band EQ with presets AND per-band manual control.

VLC band indices → ISO centre frequencies:
  0=60Hz  1=170Hz  2=310Hz  3=600Hz  4=1kHz
  5=3kHz  6=6kHz   7=12kHz  8=14kHz  9=16kHz
Gain range: −20 to +20 dB.
"""

from __future__ import annotations
from smart_radio_pro.utils.logger import log


class Equalizer:
    PRESETS: dict[str, list[tuple[int, float]]] = {
        "None":         [],
        "Flat":         [(i, 0.0) for i in range(10)],
        "Bass Boost":   [(0, 15), (1, 12), (2, 8),  (3, 4)],
        "Bass Cut":     [(0,-12), (1,-8),  (2,-4)],
        "Treble Boost": [(7, 8),  (8, 12), (9, 10)],
        "Treble Cut":   [(7,-8),  (8,-10), (9,-8)],
        "Rock":         [(0, 8),  (1, 6),  (4, -2), (7, 7),  (9, 8)],
        "Pop":          [(0, 4),  (2, 5),  (3, 4),  (5, -1), (7, 6)],
        "Jazz":         [(1, 5),  (3, 3),  (6, 4),  (8, 3)],
        "Classical":    [(2, 4),  (5, 3),  (6, 2)],
        "Dance":        [(0, 10), (3, -3), (6, 6),  (9, 8)],
        "Vocal Boost":  [(3, 6),  (4, 8),  (5, 6)],
        "Lounge":       [(0, -4), (2, 2),  (4, 4),  (6, 2),  (9, -2)],
        "Custom":       [],    # placeholder for manual band edits
    }

    BAND_LABELS = [
        "60Hz", "170Hz", "310Hz", "600Hz", "1kHz",
        "3kHz", "6kHz",  "12kHz", "14kHz", "16kHz",
    ]

    GAIN_MIN = -20.0
    GAIN_MAX =  20.0

    def __init__(self):
        self.enabled         = False
        self.current_preset  = "None"
        self._bands: list[float] = [0.0] * 10
        self._on_change      = None

    def set_on_change_callback(self, cb):
        self._on_change = cb

    def set_preset(self, name: str):
        if name not in self.PRESETS:
            return
        self._bands = [0.0] * 10
        for idx, amp in self.PRESETS[name]:
            if 0 <= idx < 10:
                self._bands[idx] = float(max(self.GAIN_MIN, min(self.GAIN_MAX, amp)))
        self.current_preset = name
        self._notify()

    def set_band(self, band: int, gain: float):
        """Manually set one band (0-9) to a gain value. Switches preset to 'Custom'."""
        if not 0 <= band < 10:
            return
        self._bands[band] = float(max(self.GAIN_MIN, min(self.GAIN_MAX, gain)))
        self.current_preset = "Custom"
        self._notify()

    def set_all_bands(self, gains: list[float]):
        """Set all 10 bands at once. Switches preset to 'Custom'."""
        if len(gains) != 10:
            return
        self._bands = [float(max(self.GAIN_MIN, min(self.GAIN_MAX, g))) for g in gains]
        self.current_preset = "Custom"
        self._notify()

    def reset(self):
        self._bands = [0.0] * 10
        self.current_preset = "Flat"
        self._notify()

    def toggle(self, enabled: bool):
        if self.enabled != enabled:
            self.enabled = enabled
            self._notify()

    def get_bands(self) -> list[float]:
        return self._bands.copy()

    def _notify(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass
