"""
core/player.py — Thread-safe VLC-backed radio player.

Bug fixes vs v2:
  • _recover_playback: missing ':live-caching=3000' in reconnect path (now added)
  • _recover_playback finally: 'reconnecting' flag now ALWAYS cleared on all
    exit paths, not just the max-reconnect branch — prevents permanent stuck state
  • _health_loop: reads shared state under _vlc_lock to eliminate TOCTOU race
"""

from __future__ import annotations

import os, sys, threading, time
from typing import Callable, Optional

from core.api import is_safe_url
from core.config import VLC_INSTANCE_ARGS, HEALTH_INTERVAL, MAX_RECONNECT, RECONNECT_DELAYS
from core.equalizer import Equalizer
from utils.logger import log


def _ensure_vlc_path() -> None:
    """
    Locate libvlc.dll on Windows and inject its directory into PATH / DLL search.

    v11 improvements:
      • Added %ProgramFiles% / %ProgramFiles(x86)% env-var expansions as extra
        candidates (cover non-standard drive installs where C: differs).
      • Windows Registry lookup (HKLM + HKCU, 32-bit and 64-bit hives) as the
        definitive fallback — works for scoop/winget/custom-prefix installs.
      • Each candidate path is tried at most once (de-duplication via seen set).
    """
    if sys.platform != "win32":
        return

    candidates: list[str] = [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
        os.path.expandvars(r"%ProgramFiles%\VideoLAN\VLC"),
        os.path.expandvars(r"%ProgramFiles(x86)%\VideoLAN\VLC"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC"),
    ]

    # Registry fallback — covers scoop / winget / custom-location installs
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (
                r"SOFTWARE\VideoLAN\VLC",
                r"SOFTWARE\WOW6432Node\VideoLAN\VLC",
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        reg_path = winreg.QueryValueEx(key, "InstallDir")[0]
                        if reg_path:
                            candidates.append(reg_path)
                except OSError:
                    pass
    except ImportError:
        pass   # winreg not available (non-Windows env)

    seen: set[str] = set()
    for path in candidates:
        path = os.path.normpath(path)
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(os.path.join(path, "libvlc.dll")):
            env_path = os.environ.get("PATH", "")
            if path not in env_path:
                os.environ["PATH"] = path + ";" + env_path
            try:
                os.add_dll_directory(path)
            except (AttributeError, OSError):
                pass
            log(f"VLC found at: {path}", "debug")
            return

    log("VLC not found in common paths; hoping it is on PATH", "warning")


_ensure_vlc_path()

try:
    import vlc
except ImportError as _e:
    raise ImportError(
        "\n\n  python-vlc is not installed.\n"
        "  Run:  pip install python-vlc\n"
        "  Also install VLC from https://www.videolan.org/vlc/\n"
    ) from _e
except Exception as _e:
    raise RuntimeError(
        f"\n\n  Could not load libvlc: {_e}\n"
        "  Ensure VLC (64-bit) is installed and matches your Python bitness.\n"
    ) from _e


_ACTIVE_STATES = frozenset({
    vlc.State.Opening, vlc.State.Buffering,
    vlc.State.Playing, vlc.State.Paused,
})
_ERROR_STATES = frozenset({vlc.State.Error, vlc.State.Ended})
_STATE_LABELS = {
    vlc.State.NothingSpecial: "idle",    vlc.State.Opening:   "opening",
    vlc.State.Buffering:      "buffering", vlc.State.Playing: "playing",
    vlc.State.Paused:         "paused",  vlc.State.Stopped:   "stopped",
    vlc.State.Ended:          "ended",   vlc.State.Error:     "error",
}


class RadioPlayer:
    """
    Thread-safe internet radio player via libvlc.

    Public API:
      play(url)              → bool
      stop()
      is_playing()           → bool
      is_buffering()         → bool
      set_volume(0-100)
      toggle_mute()          → bool
      get_current_metadata() → {"title": str, "artist": str}
      get_current_url()      → str | None
      get_state_label()      → str
      get_reconnect_count()  → int
      set_equalizer_preset(name)
      set_eq_band(band, gain)
      toggle_equalizer(bool)
      shutdown()
    """

    def __init__(self, on_permanent_failure: Optional[Callable[[str], None]] = None):
        self._on_failure = on_permanent_failure
        self._volume     = 70
        self._muted      = False

        self.equalizer = Equalizer()
        self._eq_obj: vlc.AudioEqualizer | None = None

        self._current_url: str | None = None
        self._intentional_stop = False
        self.reconnecting      = False
        self._reconnect_count  = 0
        self._play_start       = 0.0
        self._last_buf_log     = 0.0   # rate-limit buffering log (once per 10s max)

        self._vlc_lock       = threading.RLock()
        self._reconnect_lock = threading.Lock()

        self._instance = vlc.Instance(*VLC_INSTANCE_ARGS)
        self._player   = self._instance.media_player_new()
        self._media: vlc.Media | None = None

        em = self._player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_vlc_error)
        em.event_attach(vlc.EventType.MediaPlayerEndReached,       self._on_vlc_end)
        em.event_attach(vlc.EventType.MediaPlayerPlaying,          self._on_vlc_playing)
        em.event_attach(vlc.EventType.MediaPlayerBuffering,        self._on_vlc_buffering)

        self.equalizer.set_on_change_callback(self._apply_eq)

        self._health_stop   = threading.Event()
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True, name="vlc-health")
        self._health_thread.start()
        log("VLC player ready", "info")

    # ── VLC events ────────────────────────────────────────────

    def _on_vlc_error(self, event):
        if not self._intentional_stop and self._current_url:
            log("VLC error event", "warning")
            threading.Thread(target=self._recover_playback,
                             args=("VLC error",), daemon=True, name="recover").start()

    def _on_vlc_end(self, event):
        if not self._intentional_stop and self._current_url:
            log("VLC stream ended unexpectedly", "warning")
            threading.Thread(target=self._recover_playback,
                             args=("Stream ended",), daemon=True, name="recover").start()

    def _on_vlc_playing(self, event):
        log("VLC: playing", "debug")
        if self._reconnect_count > 0:
            log(f"Stream recovered after {self._reconnect_count} attempt(s)", "info")
        self._reconnect_count  = 0
        self.reconnecting      = False
        self._intentional_stop = False

    def _on_vlc_buffering(self, event):
        # VLC fires buffering events continuously during live stream playback
        # (it refills the buffer while audio is already playing — this is normal).
        # Rate-limit to one log entry per 10 s to avoid flooding the log file.
        now = time.time()
        if now - self._last_buf_log >= 10.0:
            self._last_buf_log = now
            log("VLC: buffering", "debug")

    # ── Play / Stop ───────────────────────────────────────────

    def play(self, url: str) -> bool:
        if not is_safe_url(url):
            log(f"Blocked unsafe URL: {url!r}", "warning")
            return False
        with self._vlc_lock:
            self._intentional_stop = True
            self._player.stop()
            self._intentional_stop = False
            self._current_url     = url
            self._reconnect_count = 0
            self._play_start      = time.time()
            media = self._instance.media_new(url)
            media.add_option(":network-caching=3000")
            media.add_option(":live-caching=3000")
            media.add_option(":http-reconnect")
            self._player.set_media(media)
            self._media = media
            rc = self._player.play()
            if rc != 0:
                log(f"VLC play() returned {rc}", "error")
                self._current_url = None
                return False
            self._player.audio_set_volume(0 if self._muted else self._volume)
            self._apply_eq()
        log(f"Playing: {url}", "info")
        return True

    def stop(self):
        self._intentional_stop = True
        self.reconnecting      = False
        with self._vlc_lock:
            self._player.stop()
        self._current_url     = None
        self._reconnect_count = 0

    # ── Health monitor ────────────────────────────────────────

    def _health_loop(self):
        while not self._health_stop.is_set():
            time.sleep(HEALTH_INTERVAL)
            try:
                # Read shared state under lock to avoid TOCTOU race
                with self._vlc_lock:
                    intentional = self._intentional_stop
                    url         = self._current_url
                if intentional or not url:
                    continue
                state = self._player.get_state()
                if state in _ERROR_STATES and not self.reconnecting:
                    self._recover_playback(
                        f"Health: state={_STATE_LABELS.get(state, state)}")
            except Exception as e:
                # A transient libvlc error must not crash this daemon thread —
                # the next HEALTH_INTERVAL tick will retry automatically.
                log(f"Health loop error (non-fatal): {e}", "warning")

    # ── Reconnect ─────────────────────────────────────────────

    def _recover_playback(self, reason: str) -> None:
        if self._intentional_stop or not self._current_url:
            return
        if not self._reconnect_lock.acquire(blocking=False):
            return
        try:
            self.reconnecting      = True
            self._reconnect_count += 1
            if self._reconnect_count > MAX_RECONNECT:
                log(f"{reason} — max reconnects reached", "error")
                url = self._current_url
                self.stop()
                if self._on_failure and url:
                    self._on_failure(url)
                return
            delay = RECONNECT_DELAYS[
                min(self._reconnect_count - 1, len(RECONNECT_DELAYS) - 1)]
            log(f"{reason} — reconnect in {delay}s "
                f"(attempt {self._reconnect_count}/{MAX_RECONNECT})", "warning")
            time.sleep(delay)
            if self._intentional_stop or not self._current_url:
                return
            url = self._current_url
            with self._vlc_lock:
                media = self._instance.media_new(url)
                media.add_option(":network-caching=3000")
                media.add_option(":live-caching=3000")   # FIX: was missing here
                media.add_option(":http-reconnect")
                self._player.set_media(media)
                self._media = media
                self._player.play()
                self._player.audio_set_volume(0 if self._muted else self._volume)
                self._apply_eq()
        finally:
            # FIX BUG 3: reconnecting is ALWAYS cleared here.
            # On success, _on_vlc_playing() also clears it (harmless double-clear).
            # On exception or any early-return, this guarantees the flag is reset.
            # Previously the `if count > MAX_RECONNECT` guard meant exceptions
            # left reconnecting=True permanently, freezing the player UI forever.
            self.reconnecting = False
            self._reconnect_lock.release()

    # ── Volume / Mute ─────────────────────────────────────────

    def set_volume(self, vol: int):
        vol = max(0, min(100, int(vol)))
        self._volume = vol
        if not self._muted:
            try:
                self._player.audio_set_volume(vol)
            except Exception as e:
                log(f"Volume error: {e}", "warning")

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        try:
            self._player.audio_set_volume(0 if self._muted else self._volume)
        except Exception as e:
            log(f"Mute error: {e}", "warning")
        return self._muted

    def fade_in(self, target_vol: int | None = None, steps: int = 20,
                interval_ms: float = 0.04) -> None:
        """Smoothly ramp volume from 0 → target (non-blocking thread)."""
        target = max(0, min(100, int(target_vol if target_vol is not None else self._volume)))
        def _fade():
            for i in range(1, steps + 1):
                if self._intentional_stop:
                    break
                v = int(target * i / steps)
                try:
                    if not self._muted:
                        self._player.audio_set_volume(v)
                except Exception:
                    break
                time.sleep(interval_ms)
            # Ensure final value is set
            if not self._intentional_stop and not self._muted:
                try:
                    self._player.audio_set_volume(target)
                except Exception:
                    pass
        threading.Thread(target=_fade, daemon=True, name="fade-in").start()

    def fade_out(self, callback=None, steps: int = 18, interval_ms: float = 0.035) -> None:
        """Smoothly ramp volume from current → 0, then call optional callback."""
        start_vol = self._volume
        def _fade():
            for i in range(steps, -1, -1):
                v = int(start_vol * i / steps)
                try:
                    self._player.audio_set_volume(max(0, v))
                except Exception:
                    break
                time.sleep(interval_ms)
            if callback:
                try:
                    callback()
                except Exception:
                    pass
        threading.Thread(target=_fade, daemon=True, name="fade-out").start()

    # ── State ─────────────────────────────────────────────────

    def is_playing(self) -> bool:
        if self.reconnecting:
            return True
        if self._intentional_stop or not self._current_url:
            return False
        try:
            return self._player.get_state() in _ACTIVE_STATES
        except Exception:
            return False

    def is_buffering(self) -> bool:
        try:
            return self._player.get_state() in (vlc.State.Opening, vlc.State.Buffering)
        except Exception:
            return False

    def get_state_label(self) -> str:
        if self.reconnecting:
            return "reconnecting"
        try:
            return _STATE_LABELS.get(self._player.get_state(), "unknown")
        except Exception:
            return "unknown"

    def get_current_url(self) -> str | None:
        return self._current_url

    def get_reconnect_count(self) -> int:
        return self._reconnect_count

    # ── Metadata ──────────────────────────────────────────────

    def get_current_metadata(self) -> dict:
        if not self._media:
            return {"title": "", "artist": ""}
        try:
            now_playing = (self._media.get_meta(vlc.Meta.NowPlaying) or "").strip()
            title       = (self._media.get_meta(vlc.Meta.Title)      or "").strip()
            artist      = (self._media.get_meta(vlc.Meta.Artist)     or "").strip()
            return {"title": now_playing or title, "artist": artist}
        except Exception:
            return {"title": "", "artist": ""}

    # ── Equalizer ─────────────────────────────────────────────

    def set_equalizer_preset(self, preset: str):
        self.equalizer.set_preset(preset)

    def set_eq_band(self, band: int, gain: float):
        self.equalizer.set_band(band, gain)

    def toggle_equalizer(self, enabled: bool):
        self.equalizer.toggle(enabled)

    def _apply_eq(self):
        if not self.equalizer.enabled or self.equalizer.current_preset == "None":
            try:
                self._player.set_equalizer(None)
            except Exception:
                pass
            self._eq_obj = None
            return
        try:
            eq = vlc.AudioEqualizer()
            eq.set_preamp(0.0)
            for i, gain in enumerate(self.equalizer.get_bands()):
                eq.set_amp_at_index(float(gain), i)
            self._player.set_equalizer(eq)
            self._eq_obj = eq   # keep alive — libvlc holds raw pointer
            log(f"EQ applied: {self.equalizer.current_preset}", "debug")
        except Exception as e:
            log(f"EQ apply error: {e}", "warning")

    # ── Shutdown ──────────────────────────────────────────────

    def shutdown(self):
        self._health_stop.set()
        self.stop()
        try:
            self._player.release()
            self._instance.release()
        except Exception:
            pass
        log("VLC player shut down", "info")
