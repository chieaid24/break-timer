# Repository guidance

## Scope

- Support Windows 10 and Windows 11 only.
- Keep the tray interface and configuration minimal.
- Register startup in the current user's Run key. Do not add a control that removes it.
- Treat a notification as triggered only after toast delivery returns successfully.

## Architecture

- `productivity_timer/timer.py` owns scheduling, thread lifecycle, and coherent timer snapshots.
- `productivity_timer/windows.py` owns registry, persistence, notification, mutex, and tray adapters.
- `tray_app.py` remains a compatibility entry point for PyInstaller.
- Persist user state under `%LOCALAPPDATA%/ProductivityTimer`.

## Verification

Use Python 3.12 on Windows.

```powershell
python -m pip install -r requirements-dev.txt
ruff format --check .
ruff check .
python -m unittest discover -v
pyinstaller --clean --noconfirm tray_app.spec
```

Do not commit `build/` or `dist/`; GitHub Actions verifies the Windows executable.
