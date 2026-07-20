# Repository guidance

## Scope

- Support Windows 10 and Windows 11 only.
- Keep the tray interface and configuration minimal.
- Register startup in the current user's Run key. Do not add a control that removes it.
- Treat a notification as triggered only after toast delivery returns successfully.

## Architecture

- `productivity_timer/timer.py` owns scheduling, thread lifecycle, and coherent timer snapshots.
- `productivity_timer/settings.py` owns settings validation and persistence.
- `productivity_timer/settings_dialog.py` owns the native settings window.
- `productivity_timer/windows.py` owns registry, trigger persistence, notification, mutex, and tray adapters.
- Register the notification AUMID (`APP_USER_MODEL_ID`) at launch and pass the same string to the toaster; Windows silently drops toasts from an unregistered AUMID.
- `tray_app.py` remains a compatibility entry point for PyInstaller.
- Persist user state under `%LOCALAPPDATA%/ProductivityTimer`.
- `scripts/build.ps1` is the canonical test and packaging entry point.
- `scripts/test-installer.ps1` exercises install, startup registration, and uninstall cleanup in CI only.
- `installer/ProductivityTimer.iss` owns per-user installation, startup registration, upgrades, and uninstall cleanup.
- Version tags publish the installer, portable executable, and checksums through `.github/workflows/release.yml`.

## Verification

Use Python 3.12 on Windows.

```powershell
.\scripts\install-inno.ps1
.\scripts\build.ps1
```

Do not commit `.build-assets/`, `build/`, or `dist/`; GitHub Actions verifies the Windows executable and installer.
