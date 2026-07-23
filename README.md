# Productivity Timer

Productivity Timer is a configurable break reminder. It stays out of your way —
on Windows it lives in the system tray, on macOS in the menu bar — and reminds
you to look away from the screen or take a short walking break.

Both platforms are built from the same scheduling and settings core and start
automatically when you sign in.

## Pick your platform

| | Windows 10 / 11 | macOS 13+ |
| --- | --- | --- |
| **Setup guide** | [docs/WINDOWS.md](docs/WINDOWS.md) | [docs/MACOS.md](docs/MACOS.md) |
| Where it lives | System tray | Menu bar (`⏱`), no Dock icon |
| Install with | `ProductivityTimer-Setup.exe` | `./scripts/install-macos.sh` |
| Change settings | **Settings...** in the tray menu | Edit `settings.json` |
| Notifications | Windows toast | Notification Center |
| Sounds | Windows sounds, silent, or custom WAV | Random macOS system sound, silent, or custom |
| Starts at sign-in via | `HKCU\...\Run` registry key | `launchd` user agent |
| Settings and logs | `%LOCALAPPDATA%\ProductivityTimer` | `~/Library/Application Support/ProductivityTimer` |
| Runtime | Bundled, no Python needed | Python 3.11+ in a local `.venv` |

Linux is not supported.

## Layout

```
productivity_timer/
  timer.py            scheduling, shared by both platforms
  settings.py         settings validation and persistence, shared
  __main__.py         picks the platform at launch
  windows.py          tray icon, toasts, registry startup   (Windows only)
  settings_dialog.py  the native settings window            (Windows only)
  macos.py            menu bar item, Notification Center, launch agent (macOS only)
scripts/
  build.ps1           test and package the Windows build
  install-inno.ps1    install the Windows installer toolchain
  install-macos.sh    install and start the macOS build
  uninstall-macos.sh  stop and remove the macOS build
installer/            Windows installer definition
docs/                 per-platform setup guides and release notes
```

## Verify

On Windows, from PowerShell:

```powershell
.\scripts\install-inno.ps1
.\scripts\build.ps1
```

On macOS:

```bash
.venv/bin/python -m pytest tests/test_macos.py tests/test_timer.py tests/test_settings.py
```

`tests/test_windows.py` needs Windows and runs in GitHub Actions.
