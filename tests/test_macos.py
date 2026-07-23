from __future__ import annotations

import plistlib
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from productivity_timer.settings import NotificationSound, ReminderSettings
from productivity_timer.timer import TimerSnapshot

if sys.platform == "darwin":
    from productivity_timer.macos import (
        DEFAULT_MACOS_MESSAGE,
        LAUNCH_AGENT_LABEL,
        NOTIFICATION_TITLE,
        SYSTEM_SOUNDS,
        SYSTEM_SOUNDS_DIR,
        LaunchAgentRegistration,
        NotificationCenterNotifier,
        SingleInstance,
        TriggerStateStore,
        _applescript_string,
        format_schedule,
        launch_arguments,
        resolve_sound,
        run_macos_app,
    )


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class TriggerStateStoreTests(unittest.TestCase):
    def test_saves_and_loads_an_aware_timestamp(self) -> None:
        moment = datetime(2026, 7, 23, 9, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            store = TriggerStateStore(Path(directory) / "nested" / "state.json")
            store.save(moment)
            self.assertEqual(store.load(), moment)

    def test_rejects_a_naive_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TriggerStateStore(Path(directory) / "state.json")
            with self.assertRaises(ValueError):
                store.save(datetime(2026, 7, 23, 9, 30))

    def test_missing_file_loads_as_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(TriggerStateStore(Path(directory) / "gone.json").load())

    def test_invalid_document_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertLogs("productivity_timer.macos", level="WARNING"):
                self.assertIsNone(TriggerStateStore(path).load())


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class LaunchAgentRegistrationTests(unittest.TestCase):
    def _registration(
        self, directory: str, label: str | None = None
    ) -> LaunchAgentRegistration:
        # Default resolved at call time; module constant only exists on macOS.
        label = label if label is not None else LAUNCH_AGENT_LABEL
        root = Path(directory)
        return LaunchAgentRegistration(
            ["/opt/venv/bin/python", "-m", "productivity_timer"],
            root / "repo",
            root / "launchd.log",
            root / "agents" / f"{label}.plist",
            label,
        )

    def test_definition_starts_at_sign_in_and_stays_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            definition = self._registration(directory).definition
            self.assertEqual(definition["Label"], LAUNCH_AGENT_LABEL)
            self.assertEqual(
                definition["ProgramArguments"],
                ["/opt/venv/bin/python", "-m", "productivity_timer"],
            )
            self.assertTrue(definition["RunAtLoad"])
            self.assertTrue(definition["KeepAlive"])
            self.assertTrue(definition["WorkingDirectory"].endswith("repo"))

    def test_ensure_writes_a_readable_plist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registration = self._registration(directory)
            registration.ensure()
            written = plistlib.loads(registration.plist_path.read_bytes())
            self.assertEqual(written, registration.definition)

    def test_ensure_leaves_a_matching_plist_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registration = self._registration(directory)
            registration.ensure()
            first = registration.plist_path.stat().st_mtime_ns
            registration.ensure()
            self.assertEqual(registration.plist_path.stat().st_mtime_ns, first)

    def test_ensure_replaces_a_stale_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registration = self._registration(directory)
            registration.plist_path.parent.mkdir(parents=True, exist_ok=True)
            registration.plist_path.write_bytes(
                plistlib.dumps(
                    {"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": ["old"]}
                )
            )
            registration.ensure()
            written = plistlib.loads(registration.plist_path.read_bytes())
            self.assertEqual(written["ProgramArguments"][-1], "productivity_timer")

    def test_ensure_replaces_an_unreadable_plist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registration = self._registration(directory)
            registration.plist_path.parent.mkdir(parents=True, exist_ok=True)
            registration.plist_path.write_bytes(b"not a plist")
            with self.assertLogs("productivity_timer.macos", level="WARNING"):
                registration.ensure()
            self.assertEqual(
                plistlib.loads(registration.plist_path.read_bytes()),
                registration.definition,
            )

    def test_launch_arguments_run_the_package(self) -> None:
        self.assertEqual(
            launch_arguments(executable=Path("/opt/venv/bin/python")),
            ["/opt/venv/bin/python", "-m", "productivity_timer"],
        )

    def test_launch_arguments_keep_the_virtualenv_interpreter(self) -> None:
        # Resolving the symlink would hand launchd the interpreter the venv was
        # built from, which cannot import rumps.
        with mock.patch(
            "productivity_timer.macos.sys.executable",
            "/repo/.venv/bin/python",
        ):
            self.assertEqual(launch_arguments()[0], "/repo/.venv/bin/python")


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class SingleInstanceTests(unittest.TestCase):
    def test_second_acquire_is_refused_while_the_first_holds_the_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.lock"
            with SingleInstance(path) as first:
                self.assertTrue(first.acquire())
                second = SingleInstance(path)
                self.assertFalse(second.acquire())

    def test_the_lock_is_reusable_after_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.lock"
            first = SingleInstance(path)
            self.assertTrue(first.acquire())
            first.close()
            second = SingleInstance(path)
            self.assertTrue(second.acquire())
            second.close()


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class SoundTests(unittest.TestCase):
    def test_silent_plays_nothing(self) -> None:
        settings = ReminderSettings(sound=NotificationSound.SILENT)
        self.assertIsNone(resolve_sound(settings))

    def test_custom_sound_is_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            custom = Path(directory) / "chime.wav"
            custom.write_bytes(b"")
            settings = ReminderSettings(
                sound=NotificationSound.CUSTOM, custom_sound=custom
            )
            self.assertEqual(resolve_sound(settings), custom)

    def test_missing_custom_sound_falls_back_to_a_system_sound(self) -> None:
        settings = ReminderSettings(
            sound=NotificationSound.CUSTOM,
            custom_sound=Path("/nowhere/chime.wav"),
        )
        with self.assertLogs("productivity_timer.macos", level="WARNING"):
            resolved = resolve_sound(settings)
        self.assertEqual(resolved.parent, SYSTEM_SOUNDS_DIR)

    def test_default_picks_an_installed_system_sound(self) -> None:
        resolved = resolve_sound(ReminderSettings())
        self.assertEqual(resolved.parent, SYSTEM_SOUNDS_DIR)
        self.assertIn(resolved.stem, SYSTEM_SOUNDS)
        self.assertTrue(resolved.is_file(), f"{resolved} is not installed")


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class NotifierTests(unittest.TestCase):
    def test_notify_sends_the_message_to_notification_center(self) -> None:
        notifier = NotificationCenterNotifier(
            ReminderSettings(message="Stand up", sound=NotificationSound.SILENT)
        )
        with mock.patch("productivity_timer.macos.subprocess.run") as run:
            notifier.notify()
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[0], "osascript")
        self.assertIn('"Stand up"', command[2])
        self.assertIn(f'"{NOTIFICATION_TITLE}"', command[2])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_notify_plays_the_resolved_sound(self) -> None:
        notifier = NotificationCenterNotifier(ReminderSettings())
        with mock.patch("productivity_timer.macos.subprocess.run") as run:
            notifier.notify()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[1].args[0][0], "afplay")

    def test_a_failing_sound_does_not_fail_the_reminder(self) -> None:
        notifier = NotificationCenterNotifier(ReminderSettings())
        with (
            mock.patch(
                "productivity_timer.macos.subprocess.run",
                side_effect=[mock.DEFAULT, OSError("afplay is missing")],
            ),
            self.assertLogs("productivity_timer.macos", level="ERROR"),
        ):
            notifier.notify()

    def test_configure_replaces_the_message(self) -> None:
        notifier = NotificationCenterNotifier(ReminderSettings(message="First"))
        notifier.configure(
            ReminderSettings(message="Second", sound=NotificationSound.SILENT)
        )
        with mock.patch("productivity_timer.macos.subprocess.run") as run:
            notifier.notify()
        self.assertIn('"Second"', run.call_args.args[0][2])

    def test_quotes_in_the_message_are_escaped(self) -> None:
        self.assertEqual(_applescript_string('say "hi"'), '"say \\"hi\\""')
        self.assertEqual(_applescript_string("back\\slash"), '"back\\\\slash"')

    def test_the_default_message_matches_the_original_mac_reminder(self) -> None:
        self.assertEqual(DEFAULT_MACOS_MESSAGE, "Water, posture, eyes, and bridge")


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class ScheduleFormatTests(unittest.TestCase):
    def test_a_paused_timer_reports_no_next_reminder(self) -> None:
        now = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
        snapshot = TimerSnapshot(running=False, last_triggered=None, next_trigger=None)
        self.assertEqual(format_schedule(snapshot, now), "Last: never · Next: paused")

    def test_today_is_reported_as_a_time_of_day(self) -> None:
        now = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
        snapshot = TimerSnapshot(
            running=True,
            last_triggered=now - timedelta(minutes=5),
            next_trigger=now + timedelta(minutes=15),
        )
        self.assertEqual(
            format_schedule(snapshot, now),
            "Last: today at 09:55:00 · Next: today at 10:15:00",
        )

    def test_an_older_reminder_is_reported_with_its_date(self) -> None:
        now = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
        snapshot = TimerSnapshot(
            running=True,
            last_triggered=now - timedelta(days=1),
            next_trigger=now + timedelta(minutes=15),
        )
        self.assertIn("2026-07-22 10:00:00", format_schedule(snapshot, now))


@unittest.skipUnless(sys.platform == "darwin", "macOS module")
class EntryPointTests(unittest.TestCase):
    def test_the_app_refuses_to_run_off_macos(self) -> None:
        with (
            mock.patch("productivity_timer.macos.sys.platform", "win32"),
            self.assertRaises(OSError),
        ):
            run_macos_app()


if __name__ == "__main__":
    unittest.main()
