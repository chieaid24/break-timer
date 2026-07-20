# Productivity Timer

Productivity Timer is a configurable break reminder for Windows 10 and Windows 11. It runs in the system tray and starts automatically at sign-in. I use it to remind myself to look away from the screen or take a short walking break.

This app does not support macOS or Linux.

## Install

1. Open the [latest release](https://github.com/chieaid24/break-timer-app/releases/latest). Sign in to GitHub if asked.
2. Download `ProductivityTimer-Setup.exe`.
3. Open the downloaded file. If Windows SmartScreen appears, click **More info**, confirm the filename, then click **Run anyway**. Do not turn off SmartScreen.
4. Complete the installer. Productivity Timer starts immediately and will start at every Windows sign-in.

The first unsigned release may show a SmartScreen warning. A managed work or school computer can block the override; in that case, ask its administrator.

After the installer works, delete your old downloaded `ProductivityTimer.exe` or old project folder. The installer replaces the previous startup entry. If an old tray icon is still visible, right-click it and choose **Quit until next sign-in** first.

## Use

Right-click the tray icon and choose **Settings...** to change the break interval, notification message, and sound. Choose a built-in Windows sound, silent mode, or a custom WAV file. Saving a changed interval restarts the current countdown.

Hover over the tray icon to see the last successful reminder and the next scheduled reminder. Click the icon to pause or resume reminders. Pausing lasts until you resume or restart the app; quitting lasts until your next Windows sign-in.

Logs, settings, and the last successful trigger are stored in `%LOCALAPPDATA%\ProductivityTimer`.

To remove the app, open **Settings > Apps > Installed apps**, find **Productivity Timer**, and click **Uninstall**.

## Build

Use Windows and Python 3.12. Run these commands from PowerShell:

```powershell
.\scripts\install-inno.ps1
.\scripts\build.ps1
```

The script creates `dist\ProductivityTimer.exe` and `dist\installer\ProductivityTimer-Setup.exe`. A pushed version tag such as `v1.0.0` runs the same checks and publishes both files to GitHub Releases.
