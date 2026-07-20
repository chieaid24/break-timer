"""Validated reminder settings and persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from productivity_timer import DEFAULT_INTERVAL_MINUTES, DEFAULT_MESSAGE

logger = logging.getLogger(__name__)

MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 1440
MAX_MESSAGE_LENGTH = 500


class NotificationSound(StrEnum):
    """Supported Windows notification sound choices."""

    DEFAULT = "default"
    REMINDER = "reminder"
    MAIL = "mail"
    INSTANT_MESSAGE = "instant_message"
    TEXT_MESSAGE = "text_message"
    SILENT = "silent"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    """User-configurable reminder behavior."""

    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    message: str = DEFAULT_MESSAGE
    sound: NotificationSound = NotificationSound.DEFAULT
    custom_sound: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.interval_minutes, int) or isinstance(
            self.interval_minutes, bool
        ):
            raise ValueError("Interval must be a whole number.")
        if not MIN_INTERVAL_MINUTES <= self.interval_minutes <= MAX_INTERVAL_MINUTES:
            raise ValueError(
                f"Interval must be between {MIN_INTERVAL_MINUTES} and "
                f"{MAX_INTERVAL_MINUTES} minutes."
            )
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("Message cannot be empty.")
        if len(self.message) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer."
            )
        if not isinstance(self.sound, NotificationSound):
            raise ValueError("Choose a listed sound.")
        if self.custom_sound is not None and not isinstance(self.custom_sound, Path):
            raise ValueError("Custom sound path is invalid.")
        if self.sound is NotificationSound.CUSTOM:
            if self.custom_sound is None:
                raise ValueError("Choose a custom WAV file.")
            if self.custom_sound.suffix.lower() != ".wav":
                raise ValueError("Custom sound must be a WAV file.")


class SettingsStore:
    """Persist reminder settings as an atomic JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ReminderSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings document must be an object")
            custom_sound = raw.get("custom_sound")
            return ReminderSettings(
                interval_minutes=raw.get("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                message=raw.get("message", DEFAULT_MESSAGE),
                sound=NotificationSound(
                    raw.get("sound", NotificationSound.DEFAULT.value)
                ),
                custom_sound=Path(custom_sound) if custom_sound else None,
            )
        except FileNotFoundError:
            return ReminderSettings()
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            logger.warning("Ignoring invalid reminder settings at %s", self.path)
            return ReminderSettings()

    def save(self, settings: ReminderSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "interval_minutes": settings.interval_minutes,
            "message": settings.message,
            "sound": settings.sound.value,
            "custom_sound": (
                str(settings.custom_sound)
                if settings.custom_sound is not None
                else None
            ),
        }
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)
