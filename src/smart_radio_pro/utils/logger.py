import logging
import os
from logging.handlers import RotatingFileHandler

_ROOT    = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.normpath(os.path.join(_ROOT, ".."))
_LOG_FILE = os.path.join(_LOG_DIR, "radio_log.txt")

_logger = logging.getLogger("radio")

if not _logger.handlers:
    _logger.setLevel(logging.DEBUG)
    _fh = RotatingFileHandler(
        _LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    _fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s",
                                       datefmt="%H:%M:%S"))
    _logger.addHandler(_fh)
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                       datefmt="%H:%M:%S"))
    _logger.addHandler(_ch)


def log(msg: str, level: str = "info"):
    getattr(_logger, level, _logger.info)(msg)
