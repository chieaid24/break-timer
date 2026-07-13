# Productivity Timer

Productivity Timer is a fixed 20-minute reminder for Windows 10 and Windows 11. It runs in the system tray, sends `Water, breathe, flat, posture`, and registers itself to start at sign-in.

This app does not support macOS or Linux, and it has no interval or message settings.

## Run

Download `ProductivityTimer-windows` from the latest successful [Windows workflow](../../actions/workflows/windows.yml), extract it to a permanent location, and run `ProductivityTimer.exe`. The first launch starts the timer and registers that executable for future sign-ins.

Hover over the tray icon to see the last successful reminder and the next scheduled reminder. Click the icon to pause or resume reminders. Pausing lasts until you resume or restart the app; quitting lasts until your next Windows sign-in.

Logs and the last successful trigger are stored in `%LOCALAPPDATA%\ProductivityTimer`.

## Build

Use Python 3.12 on Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\ruff format --check .
.venv\Scripts\ruff check .
.venv\Scripts\python -m unittest discover -v
.venv\Scripts\pyinstaller --clean --noconfirm tray_app.spec
```

The executable is written to `dist\ProductivityTimer.exe`.
