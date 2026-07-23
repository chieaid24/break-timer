# Productivity Timer on macOS

The macOS build is a menu bar app. It has no Dock icon, no window, and no entry
in the app switcher — the only thing you see is the `⏱` item in the top bar,
the same way the Windows build lives only in the taskbar tray.

## Requirements

- macOS 13 or newer
- Python 3.11 or newer

macOS ships with Python 3.9, which is too old. Install a newer one first:

```bash
brew install python@3.12
```

## Install

```bash
git clone git@github-personal:chieaid24/break-timer.git
cd break-timer
./scripts/install-macos.sh
```

The script creates `.venv/`, installs the macOS dependencies, writes the launch
agent, and starts the app. The `⏱` appears in the menu bar and comes back at
every sign-in.

The first reminder asks for notification permission. Allow it, or reminders are
delivered silently to Notification Center with nothing on screen.

## Use

Click the `⏱` to open the menu:

- The first line shows the last reminder and the next one.
- **Pause reminders** stops the countdown. The title changes to `⏱ ⏸`. Pausing
  lasts until you resume or restart the app.
- **Open settings file** reveals `settings.json` in Finder.
- **Quit until next sign-in** stops the app. It returns at your next sign-in.

## Settings

Everything lives in
`~/Library/Application Support/ProductivityTimer/settings.json`:

```json
{
  "interval_minutes": 20,
  "message": "Water, posture, eyes, and bridge",
  "sound": "default",
  "custom_sound": null
}
```

- `interval_minutes` — 1 to 1440.
- `message` — the reminder text, up to 500 characters.
- `sound` — `"default"` plays a random macOS system sound from
  `/System/Library/Sounds`. `"silent"` plays nothing. `"custom"` plays
  `custom_sound`. The remaining values are Windows sound names and behave like
  `"default"` here.
- `custom_sound` — an absolute path to a `.wav` file, used only when `sound` is
  `"custom"`.

Settings are read at launch. Restart the app after editing:

```bash
launchctl kickstart -k "gui/$UID/com.chieaid24.productivitytimer"
```

## Files

| Path | Contents |
| --- | --- |
| `~/Library/Application Support/ProductivityTimer/settings.json` | Your settings |
| `~/Library/Application Support/ProductivityTimer/state.json` | Last successful reminder |
| `~/Library/Application Support/ProductivityTimer/productivity_timer.log` | Application log |
| `~/Library/Application Support/ProductivityTimer/launchd.log` | Startup errors from launchd |
| `~/Library/LaunchAgents/com.chieaid24.productivitytimer.plist` | Sign-in entry |

## Uninstall

```bash
./scripts/uninstall-macos.sh          # stop it and remove the sign-in entry
./scripts/uninstall-macos.sh --purge  # also delete settings, state, and logs
```

## Develop

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-macos.txt
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/test_macos.py tests/test_timer.py tests/test_settings.py
```

Run it in the foreground without touching your installed copy:

```bash
.venv/bin/python -m productivity_timer
```

Point `HOME` at a scratch directory to keep a test run from writing a launch
agent or settings into your real home directory:

```bash
HOME=$(mktemp -d) .venv/bin/python -m productivity_timer
```

Confirm there is no Dock icon:

```bash
osascript -e 'tell application "System Events" to get background only of ¬
    (first process whose unix id is <pid>)'
```

`true` means the app is an accessory and stays out of the Dock.
