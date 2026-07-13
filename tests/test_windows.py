from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import ModuleType
from unittest import mock

from productivity_timer.timer import TimerSnapshot
from productivity_timer.windows import (
    RUN_KEY,
    SingleInstance,
    StartupRegistration,
    ToastNotifier,
    TriggerStateStore,
    format_tooltip,
    run_windows_app,
    startup_command,
)


class NotificationSetting(Enum):
    ENABLED = 0
    DISABLED_FOR_USER = 1


class FakeToast:
    def __init__(self) -> None:
        self.text_fields: list[str] = []


class FakeNativeNotifier:
    def __init__(self, setting: NotificationSetting) -> None:
        self.setting = setting


class FakeToaster:
    def __init__(self, setting: NotificationSetting) -> None:
        self.toastNotifier = FakeNativeNotifier(setting)
        self.shown: list[FakeToast] = []

    def show_toast(self, toast: FakeToast) -> None:
        self.shown.append(toast)


class TriggerStateStoreTests(unittest.TestCase):
    def test_round_trips_timezone_aware_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TriggerStateStore(Path(directory) / "nested" / "state.json")
            triggered_at = datetime(2026, 7, 13, 14, 5, 6, tzinfo=UTC)

            store.save(triggered_at)

            self.assertEqual(store.load(), triggered_at)

    def test_ignores_invalid_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("not json", encoding="utf-8")

            with self.assertLogs("productivity_timer.windows", level="WARNING"):
                self.assertIsNone(TriggerStateStore(path).load())


class WindowsFormattingTests(unittest.TestCase):
    def test_tooltip_contains_real_last_and_next_times(self) -> None:
        now = datetime(2026, 7, 13, 14, 0, 0, tzinfo=UTC)
        snapshot = TimerSnapshot(
            running=True,
            last_triggered=datetime(2026, 7, 13, 13, 40, 1, tzinfo=UTC),
            next_trigger=datetime(2026, 7, 13, 14, 20, 2, tzinfo=UTC),
        )

        tooltip = format_tooltip(snapshot, now)

        self.assertEqual(
            tooltip,
            "Productivity Timer\nLast: today at 13:40:01\nNext: today at 14:20:02",
        )
        self.assertLessEqual(len(tooltip), 127)

    def test_tooltip_explains_never_triggered_and_paused(self) -> None:
        snapshot = TimerSnapshot(False, None, None)

        tooltip = format_tooltip(
            snapshot,
            datetime(2026, 7, 13, tzinfo=UTC),
        )

        self.assertIn("Last: never", tooltip)
        self.assertIn("Next: paused", tooltip)

    def test_frozen_startup_uses_packaged_executable(self) -> None:
        command = startup_command(
            executable=Path(
                r"C:\Program Files\Productivity Timer\ProductivityTimer.exe"
            ),
            frozen=True,
        )

        self.assertEqual(
            command,
            '"C:\\Program Files\\Productivity Timer\\ProductivityTimer.exe"',
        )

    def test_source_startup_uses_pythonw_and_entrypoint(self) -> None:
        command = startup_command(
            executable=Path(r"C:\Python312\python.exe"),
            entrypoint=Path(r"C:\Productivity Timer\tray_app.py"),
            frozen=False,
        )

        self.assertEqual(
            command,
            'C:\\Python312\\pythonw.exe "C:\\Productivity Timer\\tray_app.py"',
        )

    def test_toast_rejects_disabled_windows_notifications(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.DISABLED_FOR_USER)
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            notifier = ToastNotifier()

            with self.assertRaisesRegex(RuntimeError, "notifications are unavailable"):
                notifier.notify()

        self.assertEqual(toaster.shown, [])

    def test_toast_submits_when_windows_notifications_are_enabled(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            ToastNotifier().notify()

        self.assertEqual(
            toaster.shown[0].text_fields, ["Water, breathe, flat, posture"]
        )

    @unittest.skipIf(os.name == "nt", "non-Windows contract")
    def test_runtime_rejects_non_windows(self) -> None:
        with self.assertRaisesRegex(OSError, "Windows only"):
            run_windows_app()

    @staticmethod
    def _fake_toasts(
        setting: NotificationSetting,
    ) -> tuple[ModuleType, FakeToaster]:
        toaster = FakeToaster(setting)
        module = ModuleType("windows_toasts")
        module.Toast = FakeToast
        module.WindowsToaster = lambda application_name: toaster
        return module, toaster


@unittest.skipUnless(os.name == "nt", "Windows integration test")
class WindowsIntegrationTests(unittest.TestCase):
    def test_startup_registration_writes_real_user_run_key(self) -> None:
        import winreg

        value_name = f"ProductivityTimerTest-{uuid.uuid4()}"
        command = r'"C:\Test Path\ProductivityTimer.exe"'
        self.addCleanup(self._delete_registry_value, value_name)

        registration = StartupRegistration(command, value_name)
        registration.ensure()

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            stored, value_type = winreg.QueryValueEx(key, value_name)
        self.assertEqual(stored, command)
        self.assertEqual(value_type, winreg.REG_SZ)

        with mock.patch.object(winreg, "SetValueEx", wraps=winreg.SetValueEx) as write:
            registration.ensure()
        write.assert_not_called()

    def test_single_instance_uses_real_named_mutex(self) -> None:
        name = f"Local\\ProductivityTimerTest-{uuid.uuid4()}"
        first = SingleInstance(name)
        second = SingleInstance(name)
        self.addCleanup(second.close)
        self.addCleanup(first.close)

        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())

    @staticmethod
    def _delete_registry_value(value_name: str) -> None:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, value_name)


if __name__ == "__main__":
    unittest.main()
