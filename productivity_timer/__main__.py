"""Platform entry point. Windows runs the tray app, macOS the menu bar app."""

import sys


def main() -> int:
    if sys.platform == "darwin":
        from productivity_timer.macos import run_macos_app

        return run_macos_app()

    from productivity_timer.windows import run_windows_app

    return run_windows_app()


if __name__ == "__main__":
    raise SystemExit(main())
