# Repository guidance

## Scope

- Support Windows 10, Windows 11, and macOS 13 or newer. Do not support Linux.
- Keep both interfaces minimal: a Windows tray icon and a macOS menu bar item.
- The macOS app is an accessory app. It must never take a Dock icon, a window,
  or an app switcher entry.
- Register startup in the current user's Run key on Windows and as a `launchd`
  user agent on macOS. Do not add an in-app control that removes either one;
  removal belongs to the uninstaller.
- Treat a notification as triggered only after delivery returns successfully.

## Architecture

- `productivity_timer/timer.py` owns scheduling, thread lifecycle, and coherent
  timer snapshots. It is platform-neutral; keep it that way.
- `productivity_timer/settings.py` owns settings validation and persistence, and
  is shared by both platforms.
- `productivity_timer/__main__.py` selects the platform at launch.
- `productivity_timer/settings_dialog.py` owns the native Windows settings window.
- `productivity_timer/windows.py` owns registry, trigger persistence,
  notification, mutex, and tray adapters.
- `productivity_timer/macos.py` owns the launch agent, trigger persistence,
  Notification Center delivery, the instance lock, and menu bar adapters.
- Register the notification AUMID (`APP_USER_MODEL_ID`) at launch on Windows and
  pass the same string to the toaster; Windows silently drops toasts from an
  unregistered AUMID.
- `tray_app.py` remains a compatibility entry point for PyInstaller on Windows.
- Persist user state under `%LOCALAPPDATA%/ProductivityTimer` on Windows and
  `~/Library/Application Support/ProductivityTimer` on macOS.
- `scripts/build.ps1` is the canonical Windows test and packaging entry point.
- `scripts/install-macos.sh` is the canonical macOS install entry point.
- `scripts/test-installer.ps1` exercises install, startup registration, and
  uninstall cleanup in CI only.
- `installer/ProductivityTimer.iss` owns per-user installation, startup
  registration, upgrades, and uninstall cleanup on Windows.
- Version tags publish the installer, portable executable, and checksums through
  `.github/workflows/release.yml`.

## macOS specifics

- Cocoa is not thread safe. The reminder thread records a snapshot; only the
  `rumps.Timer` running on the main loop touches the menu bar.
- Call `setActivationPolicy_(NSApplicationActivationPolicyAccessory)` before the
  run loop starts. `rumps` does not set an activation policy, so without this
  the app takes a Dock icon.
- The launch agent must run the interpreter from `.venv/bin/python` unresolved.
  Resolving that symlink yields the interpreter the virtualenv was built from,
  which cannot import `rumps`.
- `TriggerStateStore` is deliberately duplicated in `windows.py` and `macos.py`.
  `tests/test_windows.py` asserts its warning comes from the
  `productivity_timer.windows` logger, so extracting it would break that test
  for no behavioral gain.

## Verification

Windows, with Python 3.12:

```powershell
.\scripts\install-inno.ps1
.\scripts\build.ps1
```

macOS, with Python 3.11 or newer:

```bash
.venv/bin/python -m pytest tests/test_macos.py tests/test_timer.py tests/test_settings.py
```

Do not commit `.build-assets/`, `build/`, `dist/`, or `.venv/`; GitHub Actions
verifies the Windows executable and installer.
