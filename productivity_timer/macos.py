"""macOS integration for the reminder timer."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import plistlib
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta, tzinfo
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from productivity_timer import APP_NAME, DEFAULT_INTERVAL_MINUTES
from productivity_timer.settings import (
    NotificationSound,
    ReminderSettings,
    SettingsStore,
)
from productivity_timer.timer import ReminderTimer, TimerSnapshot

logger = logging.getLogger(__name__)

# The menu bar has no hover tooltip, so the schedule lives in the menu itself.
MENU_BAR_TITLE = "⏱"
MENU_BAR_TITLE_PAUSED = "⏱ ⏸"

NOTIFICATION_TITLE = "20s Break"
# Kept distinct from the Windows default so the Mac reminder reads exactly as
# it did before this app moved into the repository.
DEFAULT_MACOS_MESSAGE = "Water, posture, eyes, and bridge"

LAUNCH_AGENT_LABEL = "com.chieaid24.productivitytimer"

SYSTEM_SOUNDS_DIR = Path("/System/Library/Sounds")
SYSTEM_SOUNDS = (
    "Basso",
    "Blow",
    "Bottle",
    "Frog",
    "Funk",
    "Glass",
    "Hero",
    "Morse",
    "Ping",
    "Pop",
    "Purr",
    "Sosumi",
    "Submarine",
    "Tink",
)

# NSApplicationActivationPolicyAccessory. An accessory app owns a menu bar item
# but never appears in the Dock or the app switcher.
NS_APPLICATION_ACTIVATION_POLICY_ACCESSORY = 1


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


class LaunchAgentRegistration:
    """Keep the current launch command in the user's LaunchAgents directory."""

    def __init__(
        self,
        arguments: list[str],
        working_directory: Path,
        log_path: Path,
        plist_path: Path,
        label: str = LAUNCH_AGENT_LABEL,
    ) -> None:
        self.arguments = arguments
        self.working_directory = working_directory
        self.log_path = log_path
        self.plist_path = plist_path
        self.label = label

    @property
    def definition(self) -> dict[str, Any]:
        return {
            "Label": self.label,
            "ProgramArguments": self.arguments,
            # `-m productivity_timer` resolves against this directory, so the
            # agent keeps working no matter where launchd starts it.
            "WorkingDirectory": os.fspath(self.working_directory),
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(self.log_path),
            "StandardErrorPath": str(self.log_path),
        }

    def ensure(self) -> None:
        if sys.platform != "darwin":
            raise OSError("Launch agent registration requires macOS")

        definition = self.definition
        try:
            current = plistlib.loads(self.plist_path.read_bytes())
        except FileNotFoundError:
            pass
        except (OSError, plistlib.InvalidFileException):
            logger.warning(
                "Replacing the unreadable launch agent at %s", self.plist_path
            )
        else:
            if current == definition:
                return

        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.plist_path.with_suffix(self.plist_path.suffix + ".tmp")
        temporary.write_bytes(plistlib.dumps(definition))
        temporary.replace(self.plist_path)


class SingleInstance:
    """Hold an exclusive lock on a file while the application is running."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._descriptor: int | None = None

    def acquire(self) -> bool:
        if self._descriptor is not None:
            return True

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            return False

        os.ftruncate(descriptor, 0)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        self._descriptor = descriptor
        return True

    def close(self) -> None:
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class NotificationCenterNotifier:
    """Deliver the configured reminder through Notification Center."""

    def __init__(self, settings: ReminderSettings | None = None) -> None:
        self._settings = settings or ReminderSettings(message=DEFAULT_MACOS_MESSAGE)

    def configure(self, settings: ReminderSettings) -> None:
        self._settings = settings

    def notify(self) -> None:
        settings = self._settings
        # check=True keeps the timer's contract: a trigger only counts once the
        # notification was actually handed to Notification Center.
        subprocess.run(
            [
                "osascript",
                "-e",
                f"display notification {_applescript_string(settings.message)} with title {_applescript_string(NOTIFICATION_TITLE)}",
            ],
            check=True,
            capture_output=True,
        )
        sound = resolve_sound(settings)
        if sound is None:
            return
        try:
            subprocess.run(["afplay", os.fspath(sound)], check=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            logger.exception("Could not play the reminder sound")


class MacMenuBarApp:
    """Coordinate the menu bar UI through the ReminderTimer interface."""

    # Cocoa is not thread safe, so the timer thread only records the newest
    # snapshot and this interval repaints it on the main run loop.
    REFRESH_SECONDS = 1

    def __init__(
        self,
        state_store: TriggerStateStore,
        settings_store: SettingsStore,
    ) -> None:
        import rumps

        self._rumps = rumps
        self._state_store = state_store
        self._settings_store = settings_store
        self._persisted_last = state_store.load()
        self._settings = settings_store.load()
        self._notifier = NotificationCenterNotifier(self._settings)

        self._app = rumps.App(APP_NAME, title=MENU_BAR_TITLE, quit_button=None)
        self._schedule_item = rumps.MenuItem("")
        self._toggle_item = rumps.MenuItem("Pause reminders", callback=self._toggle)
        self._app.menu = [
            self._schedule_item,
            None,
            self._toggle_item,
            rumps.MenuItem("Open settings file", callback=self._open_settings),
            None,
            rumps.MenuItem("Quit until next sign-in", callback=self._quit),
        ]

        self._timer = ReminderTimer(
            timedelta(minutes=self._settings.interval_minutes),
            self._notifier.notify,
            last_triggered=self._persisted_last,
            on_change=self._on_change,
        )
        self._pending: TimerSnapshot | None = self._timer.snapshot
        self._refresh = rumps.Timer(self._apply_pending, self.REFRESH_SECONDS)

    def run(self) -> None:
        hide_dock_icon()
        self._timer.start()
        self._refresh.start()
        try:
            self._app.run()
        finally:
            self._refresh.stop()
            self._timer.shutdown()

    def _toggle(self, _: object = None) -> None:
        if self._timer.snapshot.running:
            self._timer.pause()
        else:
            self._timer.start()

    def _open_settings(self, _: object = None) -> None:
        path = self._settings_store.path
        if not path.exists():
            self._settings_store.save(self._settings)
        subprocess.run(["open", "-R", os.fspath(path)], check=False)

    def _quit(self, _: object = None) -> None:
        self._timer.shutdown()
        self._rumps.quit_application()

    def _on_change(self, snapshot: TimerSnapshot) -> None:
        if (
            snapshot.last_triggered != self._persisted_last
            and snapshot.last_triggered is not None
        ):
            try:
                self._state_store.save(snapshot.last_triggered)
            except OSError:
                logger.exception("Could not persist the last reminder trigger")
            else:
                self._persisted_last = snapshot.last_triggered

        self._pending = snapshot

    def _apply_pending(self, _: object = None) -> None:
        snapshot = self._pending
        if snapshot is None:
            return
        self._pending = None
        self._app.title = MENU_BAR_TITLE if snapshot.running else MENU_BAR_TITLE_PAUSED
        self._schedule_item.title = format_schedule(snapshot)
        self._toggle_item.title = (
            "Pause reminders" if snapshot.running else "Resume reminders"
        )


def hide_dock_icon() -> None:
    """Drop the Dock icon so the app lives only in the menu bar."""
    from AppKit import NSApplication

    NSApplication.sharedApplication().setActivationPolicy_(
        NS_APPLICATION_ACTIVATION_POLICY_ACCESSORY
    )


def resolve_sound(settings: ReminderSettings) -> Path | None:
    """Return the file to play, or None when the reminder is silent."""
    if settings.sound is NotificationSound.SILENT:
        return None
    if settings.sound is NotificationSound.CUSTOM:
        if settings.custom_sound is not None and settings.custom_sound.is_file():
            return settings.custom_sound
        logger.warning("Custom notification sound is missing; using a system sound")
    return SYSTEM_SOUNDS_DIR / f"{random.choice(SYSTEM_SOUNDS)}.aiff"


def format_schedule(snapshot: TimerSnapshot, now: datetime | None = None) -> str:
    reference = now or datetime.now(UTC)
    display_timezone = reference.tzinfo if now is not None else None
    last = _format_moment(snapshot.last_triggered, reference, "never", display_timezone)
    next_trigger = _format_moment(
        snapshot.next_trigger,
        reference,
        "paused",
        display_timezone,
    )
    return f"Last: {last} · Next: {next_trigger}"


def launch_arguments(*, executable: Path | None = None) -> list[str]:
    """Build the command the launch agent runs at sign-in."""
    # Deliberately unresolved: resolving follows .venv/bin/python back to the
    # interpreter it was built from, and that one cannot import rumps.
    executable_path = (
        os.fspath(executable) if executable is not None else sys.executable
    )
    return [executable_path, "-m", "productivity_timer"]


def package_root() -> Path:
    """Return the directory `-m productivity_timer` must run from."""
    return Path(__file__).resolve().parent.parent


def run_macos_app() -> int:
    if sys.platform != "darwin":
        raise OSError("The menu bar app supports macOS only")

    state_dir = _state_dir()
    _configure_logging(state_dir / "productivity_timer.log")
    LaunchAgentRegistration(
        launch_arguments(),
        package_root(),
        state_dir / "launchd.log",
        _launch_agent_path(),
    ).ensure()

    with SingleInstance(state_dir / "instance.lock") as instance:
        if not instance.acquire():
            logger.info("Another Productivity Timer instance is already running")
            return 0
        settings_store = SettingsStore(state_dir / "settings.json")
        _seed_settings(settings_store)
        MacMenuBarApp(
            TriggerStateStore(state_dir / "state.json"),
            settings_store,
        ).run()
    return 0


def _seed_settings(store: SettingsStore) -> None:
    """Write the macOS defaults once so the file is there to edit."""
    if store.path.exists():
        return
    try:
        store.save(
            ReminderSettings(
                interval_minutes=DEFAULT_INTERVAL_MINUTES,
                message=DEFAULT_MACOS_MESSAGE,
            )
        )
    except OSError:
        logger.exception("Could not write the default reminder settings")


def _state_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "ProductivityTimer"


def _launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


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
    display_timezone: tzinfo | None,
) -> str:
    if moment is None:
        return missing
    local = moment.astimezone(display_timezone)
    local_reference = reference.astimezone(display_timezone)
    if local.date() == local_reference.date():
        return f"today at {local:%H:%M:%S}"
    return f"{local:%Y-%m-%d %H:%M:%S}"


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
