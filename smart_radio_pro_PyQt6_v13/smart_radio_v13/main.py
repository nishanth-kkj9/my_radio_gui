"""
Smart Radio Pro v10 — main entry point (PyQt6 UI).
Run with:  python main.py

Requirements:
  pip install -r requirements.txt
  VLC media player: https://www.videolan.org/vlc/

v10 bug fixes & improvements:
  • FIXED: Mini player thumbnail never showed — logo was only pre-loaded when
    mini player was already open at play-time. Now always pre-loaded unconditionally.
  • FIXED: _load_thumb_logo and _load_mini_logo never wrote logos to SQLite cache —
    every app restart re-downloaded logos from the network. Now both call db_logo_put().
  • FIXED: _stop() now clears _mini_logo_pixmap so mini player shows default logo
    after stopping (previously kept showing last station's logo).
  • FIXED: Mini player position (mini_pos) was in session defaults but never
    saved or restored — position now persists across launches.
  • FIXED: _now_thumb cursor + hover feedback only active while a station is playing.
  • FIXED: Unused imports QSize, QSizePolicy removed from app_ui.py.
  • FIXED: Hardcoded timer label color replaced with TEXT_DIM theme constant.
  • PERF: SpectrumWidget bar/reflect/peak colors are now pre-calculated LUTs
    (256 entries each) — eliminates ~240 QColor allocations per second.
  • UI: Mini player width 370→440 px; controls section fixed width prevents
    long station names from overlapping buttons.
  • UI: Station card border-radius 0→8 px for polished rounded look.
  • UI: Tooltips on all header icon buttons and mini player controls.
  • UI: ICY track label max-width 300→420 px (was clipping long track names).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui.app_ui import RadioUI


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Smart Radio Pro")
    app.setApplicationVersion("11.0")

    window = RadioUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
