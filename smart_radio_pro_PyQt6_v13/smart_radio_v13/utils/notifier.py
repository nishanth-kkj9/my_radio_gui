"""
utils/notifier.py — Cross-platform desktop notification helper (v6).

No extra pip packages required — uses only stdlib subprocess + sys.
Works on Windows (PowerShell), macOS (osascript), Linux (notify-send).

Public API:
    notify(title, message, timeout=5)  → None   (fire-and-forget, debounced)
    set_enabled(bool)                  → None
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from utils.logger import log

_enabled     = True
_last_sent   = 0.0
_MIN_GAP_S   = 20.0     # max one notification per 20 seconds


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value


def notify(title: str, message: str, timeout: int = 5) -> None:
    """Show a desktop OS notification (debounced, non-blocking)."""
    global _last_sent
    if not _enabled:
        return
    now = time.time()
    if now - _last_sent < _MIN_GAP_S:
        return
    _last_sent = now
    threading.Thread(target=_send, args=(title, message, timeout),
                     daemon=True, name="notifier").start()


def _send(title: str, message: str, timeout: int) -> None:
    try:
        if sys.platform == "win32":
            _win(title, message, timeout)
        elif sys.platform == "darwin":
            _mac(title, message)
        else:
            _linux(title, message, timeout)
    except FileNotFoundError:
        pass          # notify-send / osascript / powershell not available
    except Exception as e:
        log(f"Notification send error: {e}", "debug")


def _win(title: str, message: str, timeout: int) -> None:
    # PowerShell balloon tooltip — zero extra dependencies
    t   = title.replace('"', "'")
    m   = message.replace('"', "'")
    ms  = timeout * 1000
    ps  = (
        f'Add-Type -AssemblyName System.Windows.Forms;'
        f'$n = New-Object System.Windows.Forms.NotifyIcon;'
        f'$n.Icon = [System.Drawing.SystemIcons]::Information;'
        f'$n.Visible = $true;'
        f'$n.ShowBalloonTip({ms}, "{t}", "{m}", '
        f'[System.Windows.Forms.ToolTipIcon]::None);'
        f'Start-Sleep -Milliseconds {ms + 500};'
        f'$n.Dispose()'
    )
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000,   # CREATE_NO_WINDOW
    )


def _mac(title: str, message: str) -> None:
    t = title.replace('"', '\\"')
    m = message.replace('"', '\\"')
    subprocess.Popen(
        ["osascript", "-e", f'display notification "{m}" with title "{t}"'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _linux(title: str, message: str, timeout: int) -> None:
    subprocess.Popen(
        ["notify-send", "-t", str(timeout * 1000), "--", title, message],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
