from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from productivity_timer import DEFAULT_INTERVAL_MINUTES, DEFAULT_MESSAGE
from productivity_timer.settings import (
    NotificationSound,
    ReminderSettings,
    SettingsStore,
)
from productivity_timer.settings_dialog import settings_from_values


class ReminderSettingsTests(unittest.TestCase):
    def test_store_round_trips_all_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "settings.json"
            settings = ReminderSettings(
                interval_minutes=35,
                message="Look away from the screen",
                sound=NotificationSound.CUSTOM,
                custom_sound=Path(directory) / "soft-tone.wav",
            )
            store = SettingsStore(path)

            store.save(settings)

            self.assertEqual(store.load(), settings)

    def test_store_uses_defaults_for_invalid_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertLogs("productivity_timer.settings", level="WARNING"):
                settings = SettingsStore(path).load()

        self.assertEqual(settings.interval_minutes, DEFAULT_INTERVAL_MINUTES)
        self.assertEqual(settings.message, DEFAULT_MESSAGE)

    def test_rejects_out_of_range_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 1440"):
            ReminderSettings(interval_minutes=0)

    def test_rejects_empty_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            ReminderSettings(message="  ")


class SettingsDialogValueTests(unittest.TestCase):
    def test_builds_builtin_sound_settings(self) -> None:
        settings = settings_from_values(
            "45",
            "  Take a break  ",
            "Reminder",
            "",
        )

        self.assertEqual(settings.interval_minutes, 45)
        self.assertEqual(settings.message, "Take a break")
        self.assertIs(settings.sound, NotificationSound.REMINDER)

    def test_accepts_existing_custom_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sound = Path(directory) / "tone.wav"
            sound.write_bytes(b"RIFF")

            settings = settings_from_values(
                "20",
                "Take a break",
                "Custom WAV",
                str(sound),
            )

        self.assertEqual(settings.custom_sound, sound)

    def test_rejects_missing_custom_wav(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing custom WAV"):
            settings_from_values(
                "20",
                "Take a break",
                "Custom WAV",
                "missing.wav",
            )


if __name__ == "__main__":
    unittest.main()
