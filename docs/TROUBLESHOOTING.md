# Troubleshooting

## VLC cannot be loaded

### Symptoms

You see an error mentioning `python-vlc`, `libvlc`, or VLC being unavailable.

### Checks

1. Install VLC Media Player separately.
2. Make sure the VLC architecture matches your Python architecture.
3. On Windows, verify that VLC is installed in a standard location or is reachable through `PATH`.
4. Restart the application after installing VLC.

The player contains Windows DLL discovery for common installation directories, registry entries, and `where vlc` fallback.

## The application starts but no stations appear

Check:

1. Internet connectivity.
2. Whether Radio Browser is reachable.
3. Application logs in `src/smart_radio_pro/radio_log.txt`.
4. Press `R` to refresh the current category.
5. Try another category.

The Radio Browser client rotates through multiple API mirrors and retries selected transient HTTP failures.

## A station opens but does not play

Possible causes:

- the station stream is offline;
- the stream URL is invalid or no longer supported;
- the station requires a codec or transport unavailable to the current VLC build;
- network conditions prevent continuous buffering.

The player validates stream schemes before handing the URL to VLC.

## Playback disconnects repeatedly

The player has a background health monitor and bounded reconnect behavior. It retries up to the configured maximum and then reports a permanent failure to the UI.

Review the log for messages containing:

```text
reconnect
VLC error
Stream ended
Health:
```

## Station logos are missing

Logo loading uses:

1. memory cache;
2. SQLite cache;
3. network download.

A logo can fail because the station advertises an invalid favicon URL, the remote server rejects the request, the image is malformed, or the download exceeds the configured byte cap.

A logo URL that fails is remembered for the current session to avoid repeated requests.

## Reset the logo cache

Close the application, then remove:

```text
src/smart_radio_pro/logos.db
```

The database is recreated automatically on the next launch.

## Favorites/recent/session data is corrupted

The application is defensive about malformed JSON and falls back to defaults for invalid session data.

The affected runtime files are:

```text
src/smart_radio_pro/favorites.json
src/smart_radio_pro/recent.json
src/smart_radio_pro/session.json
src/smart_radio_pro/stats.json
```

Back up a file before deleting it if you want to preserve data for investigation.

## The mini-player does not restore its position

The mini-player stores the last position in session state and restores it on the next opening. Check that `session.json` can be read and written by the current user account.

## Volume control feels unusual

Volume can be changed through:

- the main slider;
- `↑` / `↓`;
- mouse wheel over the header;
- mouse wheel over the now-playing area;
- the mini-player slider.

The keyboard and wheel increment is controlled by `VOLUME_STEP`.

## Search returns no results

Search is performed locally against the currently loaded station set. It matches:

- station name;
- country;
- tags;
- language.

It is not a separate global search engine. Change category or refresh the category first.

## Windows Qt stylesheet warnings

The application intentionally avoids custom QSS styling for certain `QSlider` sub-controls because the current codebase found those rules unreliable on Windows/Qt6. Native Fusion controls are used for affected sliders.

## Logs

The rotating log is:

```text
src/smart_radio_pro/radio_log.txt
```

It keeps a bounded history rather than growing indefinitely.

## CI failures

The current workflow expects:

- Python 3.11 in CI;
- system VLC;
- headless Qt libraries;
- a successful editable installation;
- Ruff passing;
- both player/core imports succeeding.

A CI failure is not the same as a runtime playback failure; check the failed stage first.
