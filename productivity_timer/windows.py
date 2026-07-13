"""Windows integration for the reminder timer."""

from __future__ import annotations

import ctypes
import json
import logging
import ntpath
import os
import subprocess
import sys
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from productivity_timer import APP_NAME, DEFAULT_INTERVAL_MINUTES, DEFAULT_MESSAGE
from productivity_timer.timer import ReminderTimer, TimerSnapshot

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "ProductivityTimer"
ERROR_ALREADY_EXISTS = 183


class TriggerStateStore:
    """Persist the last successful trigger behind a two-method interface."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> datetime | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            value = datetime.fromisoformat(raw["last_triggered"])
            if value.tzinfo is None:
                raise ValueError("timestamp has no timezone")
            return value
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Ignoring invalid reminder state at %s", self.path)
            return None

    def save(self, triggered_at: datetime) -> None:
        if triggered_at.tzinfo is None:
            raise ValueError("triggered_at must include a timezone")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"last_triggered": triggered_at.isoformat()}
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class StartupRegistration:
    """Keep the current launch command in the current user's Run key."""

    def __init__(self, command: str, value_name: str = RUN_VALUE_NAME) -> None:
        self.command = command
        self.value_name = value_name

    def ensure(self) -> None:
        if os.name != "nt":
            raise OSError("Windows startup registration requires Windows")

        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                self.value_name,
                0,
                winreg.REG_SZ,
                self.command,
            )


class SingleInstance:
    """Hold a process-wide Windows mutex while the application is running."""

    def __init__(self, name: str = "Local\\ProductivityTimer") -> None:
        self.name = name
        self._kernel32: Any = None
        self._handle: int | None = None

    def acquire(self) -> bool:
        if os.name != "nt":
            raise OSError("Single-instance protection requires Windows")
        if self._handle is not None:
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._kernel32 = kernel32
        self._handle = handle
        return True

    def close(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
            self._kernel32 = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class ToastNotifier:
    """Deliver the configured reminder with the Windows toast API."""

    def __init__(self) -> None:
        from windows_toasts import WindowsToaster

        self._toaster = WindowsToaster(APP_NAME)

    def notify(self) -> None:
        from windows_toasts import Toast

        toast = Toast()
        toast.text_fields = [DEFAULT_MESSAGE]
        self._toaster.show_toast(toast)


class WindowsTrayApp:
    """Coordinate the tray UI through the ReminderTimer interface."""

    def __init__(self, state_store: TriggerStateStore) -> None:
        import pystray

        self._state_store = state_store
        self._persisted_last = state_store.load()
        self._notifier = ToastNotifier()
        self._icon = pystray.Icon("productivity_timer")
        self._timer = ReminderTimer(
            timedelta(minutes=DEFAULT_INTERVAL_MINUTES),
            self._notifier.notify,
            last_triggered=self._persisted_last,
            on_change=self._on_change,
        )
        self._icon.icon = create_status_icon(False)
        self._icon.title = format_tooltip(self._timer.snapshot)
        self._icon.menu = pystray.Menu(
            pystray.MenuItem(self._toggle_label, self._toggle, default=True),
            pystray.MenuItem("Quit until next sign-in", self._quit),
        )

    def run(self) -> None:
        self._timer.start()
        try:
            self._icon.run()
        finally:
            self._timer.shutdown()

    def _toggle_label(self, item: object) -> str:
        if self._timer.snapshot.running:
            return "Pause reminders"
        return "Resume reminders"

    def _toggle(self, icon: object = None, item: object = None) -> None:
        if self._timer.snapshot.running:
            self._timer.pause()
        else:
            self._timer.start()

    def _quit(self, icon: object = None, item: object = None) -> None:
        self._timer.shutdown()
        self._icon.stop()

    def _on_change(self, snapshot: TimerSnapshot) -> None:
        if snapshot.last_triggered != self._persisted_last:
            if snapshot.last_triggered is not None:
                try:
                    self._state_store.save(snapshot.last_triggered)
                except OSError:
                    logger.exception("Could not persist the last reminder trigger")
                else:
                    self._persisted_last = snapshot.last_triggered

        self._icon.title = format_tooltip(snapshot)
        self._icon.icon = create_status_icon(snapshot.running)
        if self._icon.visible:
            self._icon.update_menu()


def create_status_icon(is_running: bool) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=(30, 30, 30, 255))
    color = (46, 204, 113, 255) if is_running else (231, 76, 60, 255)
    draw.ellipse((40, 40, 60, 60), fill=color)
    draw.text((14, 18), "PT", fill=(240, 240, 240, 255))
    return image


def format_tooltip(snapshot: TimerSnapshot, now: datetime | None = None) -> str:
    reference = now or datetime.now().astimezone()
    last = _format_moment(snapshot.last_triggered, reference, "never")
    next_trigger = _format_moment(snapshot.next_trigger, reference, "paused")
    return f"{APP_NAME}\nLast: {last}\nNext: {next_trigger}"


def startup_command(
    *,
    executable: Path | None = None,
    entrypoint: Path | None = None,
    frozen: bool | None = None,
) -> str:
    executable_path = (
        os.fspath(executable)
        if executable is not None
        else str(Path(sys.executable).resolve())
    )
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        arguments = [executable_path]
    else:
        if ntpath.basename(executable_path).lower() in {"python.exe", "python3.exe"}:
            executable_path = ntpath.join(
                ntpath.dirname(executable_path),
                "pythonw.exe",
            )
        source = (
            os.fspath(entrypoint)
            if entrypoint is not None
            else str(Path(sys.argv[0]).resolve())
        )
        arguments = [executable_path, source]
    return subprocess.list2cmdline(arguments)


def run_windows_app() -> int:
    if os.name != "nt":
        raise OSError("Productivity Timer supports Windows only")

    state_dir = _state_dir()
    _configure_logging(state_dir / "productivity_timer.log")
    StartupRegistration(startup_command()).ensure()

    with SingleInstance() as instance:
        if not instance.acquire():
            logger.info("Another Productivity Timer instance is already running")
            return 0
        WindowsTrayApp(TriggerStateStore(state_dir / "state.json")).run()
    return 0


def _state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set")
    return Path(local_app_data) / "ProductivityTimer"


def _configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=256_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _format_moment(
    moment: datetime | None,
    reference: datetime,
    missing: str,
) -> str:
    if moment is None:
        return missing
    local = moment.astimezone(reference.tzinfo)
    if local.date() == reference.date():
        return f"today at {local:%H:%M:%S}"
    return f"{local:%Y-%m-%d %H:%M:%S}"
