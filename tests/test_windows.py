from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from types import ModuleType
from unittest import mock

from productivity_timer.settings import (
    NotificationSound,
    ReminderSettings,
    SettingsStore,
)
from productivity_timer.timer import TimerSnapshot
from productivity_timer.windows import (
    RUN_KEY,
    AppUserModelRegistration,
    SingleInstance,
    StartupRegistration,
    ToastNotifier,
    TriggerStateStore,
    WindowsTrayApp,
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
        self.audio: FakeToastAudio | None = None


class FakeAudioSource(Enum):
    Default = "Default"
    Reminder = "Reminder"
    Mail = "Mail"
    IM = "IM"
    SMS = "SMS"


class FakeToastAudio:
    def __init__(
        self,
        sound: FakeAudioSource | Path = FakeAudioSource.Default,
        *,
        silent: bool = False,
    ) -> None:
        self.sound = sound
        self.silent = silent


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

    def test_toast_still_shows_when_setting_reports_disabled(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.DISABLED_FOR_USER)
        with (
            mock.patch.dict(sys.modules, {"windows_toasts": fake_module}),
            self.assertLogs("productivity_timer.windows", level="WARNING"),
        ):
            ToastNotifier().notify()

        self.assertEqual(len(toaster.shown), 1)

    def test_toast_still_shows_when_setting_query_raises(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)

        class RaisingNotifier:
            @property
            def setting(self) -> NotificationSetting:
                raise OSError("Element not found")

        toaster.toastNotifier = RaisingNotifier()
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            ToastNotifier().notify()

        self.assertEqual(len(toaster.shown), 1)

    def test_toast_submits_when_windows_notifications_are_enabled(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            ToastNotifier().notify()

        self.assertEqual(
            toaster.shown[0].text_fields, ["Water, breathe, flat, posture"]
        )
        self.assertEqual(toaster.shown[0].audio.sound, FakeAudioSource.Default)

    def test_toast_uses_configured_message_and_builtin_sound(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        settings = ReminderSettings(
            interval_minutes=45,
            message="Stand up and stretch",
            sound=NotificationSound.REMINDER,
        )
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            ToastNotifier(settings).notify()

        self.assertEqual(toaster.shown[0].text_fields, ["Stand up and stretch"])
        self.assertEqual(toaster.shown[0].audio.sound, FakeAudioSource.Reminder)

    def test_toast_can_be_silent(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        settings = ReminderSettings(sound=NotificationSound.SILENT)
        with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
            ToastNotifier(settings).notify()

        self.assertTrue(toaster.shown[0].audio.silent)

    def test_missing_custom_sound_falls_back_to_default(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        settings = ReminderSettings(
            sound=NotificationSound.CUSTOM,
            custom_sound=Path("missing.wav"),
        )
        with (
            mock.patch.dict(sys.modules, {"windows_toasts": fake_module}),
            self.assertLogs("productivity_timer.windows", level="WARNING"),
        ):
            ToastNotifier(settings).notify()

        self.assertEqual(toaster.shown[0].audio.sound, FakeAudioSource.Default)

    def test_toast_uses_existing_custom_sound(self) -> None:
        fake_module, toaster = self._fake_toasts(NotificationSetting.ENABLED)
        with tempfile.TemporaryDirectory() as directory:
            sound = Path(directory) / "tone.wav"
            sound.write_bytes(b"RIFF")
            settings = ReminderSettings(
                sound=NotificationSound.CUSTOM,
                custom_sound=sound,
            )
            with mock.patch.dict(sys.modules, {"windows_toasts": fake_module}):
                ToastNotifier(settings).notify()

        self.assertEqual(toaster.shown[0].audio.sound, sound)

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
        module.AudioSource = FakeAudioSource
        module.Toast = FakeToast
        module.ToastAudio = FakeToastAudio
        module.WindowsToaster = lambda application_name: toaster
        return module, toaster


class WindowsTrayAppTests(unittest.TestCase):
    def test_tray_menu_exposes_settings(self) -> None:
        class FakeIcon:
            def __init__(self, name: str) -> None:
                self.name = name
                self.icon: object = None
                self.menu: object = None
                self.title = ""
                self.visible = False

        class FakeMenuItem:
            def __init__(
                self,
                text: object,
                action: object,
                *,
                default: bool = False,
            ) -> None:
                self.text = text
                self.action = action
                self.default = default

        class FakeMenu:
            SEPARATOR = object()

            def __init__(self, *items: object) -> None:
                self.items = items

        pystray = ModuleType("pystray")
        pystray.Icon = FakeIcon
        pystray.Menu = FakeMenu
        pystray.MenuItem = FakeMenuItem
        toasts, unused_toaster = WindowsFormattingTests._fake_toasts(
            NotificationSetting.ENABLED
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.dict(
                sys.modules,
                {"pystray": pystray, "windows_toasts": toasts},
            ),
        ):
            state_dir = Path(directory)
            app = WindowsTrayApp(
                TriggerStateStore(state_dir / "state.json"),
                SettingsStore(state_dir / "settings.json"),
            )
            self.addCleanup(app._timer.shutdown)

        self.assertEqual(app._icon.menu.items[1].text, "Settings...")

    def test_apply_settings_persists_and_restarts_changed_interval(self) -> None:
        app = WindowsTrayApp.__new__(WindowsTrayApp)
        app._settings = ReminderSettings()
        app._settings_store = mock.Mock()
        app._notifier = mock.Mock()
        app._timer = mock.Mock()
        settings = ReminderSettings(interval_minutes=45)

        app._apply_settings(settings)

        app._settings_store.save.assert_called_once_with(settings)
        app._notifier.configure.assert_called_once_with(settings)
        app._timer.set_interval.assert_called_once_with(timedelta(minutes=45))

    def test_apply_settings_keeps_countdown_when_interval_is_unchanged(self) -> None:
        app = WindowsTrayApp.__new__(WindowsTrayApp)
        app._settings = ReminderSettings()
        app._settings_store = mock.Mock()
        app._notifier = mock.Mock()
        app._timer = mock.Mock()
        settings = ReminderSettings(message="Take a break")

        app._apply_settings(settings)

        app._timer.set_interval.assert_not_called()


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

    def test_app_user_model_registration_writes_display_name(self) -> None:
        import winreg

        app_id = f"ProductivityTimerTest.{uuid.uuid4().hex}"
        self.addCleanup(self._delete_aumid_key, app_id)

        AppUserModelRegistration(app_id, "Productivity Timer Test").ensure()

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{app_id}",
        ) as key:
            stored, value_type = winreg.QueryValueEx(key, "DisplayName")
        self.assertEqual(stored, "Productivity Timer Test")
        self.assertEqual(value_type, winreg.REG_SZ)

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

    @staticmethod
    def _delete_aumid_key(app_id: str) -> None:
        import winreg

        winreg.DeleteKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{app_id}",
        )


if __name__ == "__main__":
    unittest.main()
