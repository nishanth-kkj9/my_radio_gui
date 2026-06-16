"""
Smart Radio Pro v13.1 — main entry point (PyQt6 UI).
Run with:  python main.py

Requirements:
  pip install -r requirements.txt
  VLC media player: https://www.videolan.org/vlc/

v13.1 improvements:
  • FIXED: _make_default_logo() referenced PIL imports not available in app_ui.py
    — replaced with QPainter-based implementation that works without PIL.
  • FIXED: Global exception handler catches uncaught exceptions and logs them
    instead of silently crashing.
  • UI: Global font configuration for consistent cross-platform appearance.
  • UI: Improved toast notifications with shadow effect and better positioning.
  • UI: Keyboard shortcut hint bar now uses theme-aware colors for visibility.
  • UI: Dialog windows get subtle drop shadows for better depth perception.
  • UI: Smoother scroll behavior in the station grid.
  • STABILITY: Defensive guards around executor operations to handle shutdown.
  • STABILITY: Session read from cache instead of disk on mini-player toggle.
  • STABILITY: Thread-safe widget access with proper RuntimeError handling.
  • STABILITY: Corrupted session files auto-recover with defaults.
"""

import os
import sys
import traceback
from types import TracebackType

# Allow running directly via `python src/smart_radio_pro/main.py` without
# installing the package first. Has no effect (and is harmless) once the
# package is properly installed, e.g. via `pip install -e .`.
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from PyQt6.QtWidgets import QApplication

from smart_radio_pro.ui.app_ui import RadioUI


def _install_excepthook():
    """Log uncaught exceptions instead of silently crashing."""
    _original = sys.excepthook

    def _handler(
        etype: type[BaseException],
        evalue: BaseException,
        etb: TracebackType | None,
    ) -> None:
        from smart_radio_pro.utils.logger import log
        tb = "".join(traceback.format_exception(etype, evalue, etb))
        log(f"Uncaught exception:\n{tb}", "error")
        _original(etype, evalue, etb)

    sys.excepthook = _handler


def main():
    _install_excepthook()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Smart Radio Pro")
    app.setApplicationVersion("13.1")

    # Global font — ensure consistent rendering across platforms
    from PyQt6.QtGui import QFont
    font = QFont("Segoe UI", 9)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    window = RadioUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
