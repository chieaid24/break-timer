from __future__ import annotations

import threading
import time
import unittest
from datetime import UTC, datetime, timedelta

from productivity_timer.timer import ReminderTimer


class ReminderTimerTests(unittest.TestCase):
    def test_start_schedules_and_success_records_real_trigger(self) -> None:
        notified = threading.Event()
        timer = ReminderTimer(timedelta(milliseconds=30), notified.set)
        self.addCleanup(timer.shutdown)

        before = datetime.now().astimezone()
        timer.start()
        started = timer.snapshot

        self.assertTrue(started.running)
        self.assertIsNotNone(started.next_trigger)
        self.assertGreaterEqual(started.next_trigger, before)
        self.assertTrue(notified.wait(1))
        self.assertTrue(
            self._wait_for(lambda: timer.snapshot.last_triggered is not None)
        )
        triggered = timer.snapshot
        self.assertGreaterEqual(triggered.last_triggered, before)
        self.assertIsNotNone(triggered.next_trigger)

    def test_pause_cancels_and_resume_starts_a_full_interval(self) -> None:
        notified = threading.Event()
        timer = ReminderTimer(timedelta(milliseconds=150), notified.set)
        self.addCleanup(timer.shutdown)

        timer.start()
        timer.pause()
        paused = timer.snapshot

        self.assertFalse(paused.running)
        self.assertIsNone(paused.next_trigger)
        self.assertFalse(notified.wait(0.25))

        resumed_at = datetime.now().astimezone()
        timer.start()
        resumed = timer.snapshot
        self.assertGreaterEqual(
            resumed.next_trigger,
            resumed_at + timedelta(milliseconds=100),
        )
        self.assertTrue(notified.wait(1))

    def test_failure_does_not_record_last_and_worker_survives(self) -> None:
        first_attempt = threading.Event()
        recovered = threading.Event()
        attempts = 0

        def notify() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                first_attempt.set()
                raise RuntimeError("expected test failure")
            recovered.set()

        timer = ReminderTimer(timedelta(milliseconds=40), notify)
        self.addCleanup(timer.shutdown)
        with self.assertLogs("productivity_timer.timer", level="ERROR") as logs:
            timer.start()

            self.assertTrue(first_attempt.wait(1))
            self.assertIsNone(timer.snapshot.last_triggered)
            self.assertTrue(recovered.wait(1))
            self.assertTrue(
                self._wait_for(lambda: timer.snapshot.last_triggered is not None)
            )
        self.assertIn("Reminder notification failed", logs.output[0])

    def test_preserves_persisted_last_trigger(self) -> None:
        previous = datetime(2026, 7, 12, 8, 30, tzinfo=UTC)
        timer = ReminderTimer(timedelta(hours=1), lambda: None, last_triggered=previous)
        self.addCleanup(timer.shutdown)

        self.assertEqual(timer.snapshot.last_triggered, previous)

    def test_shutdown_is_idempotent_and_prevents_restart(self) -> None:
        timer = ReminderTimer(timedelta(seconds=1), lambda: None)
        timer.shutdown()
        timer.shutdown()

        with self.assertRaisesRegex(RuntimeError, "shut down"):
            timer.start()

    @staticmethod
    def _wait_for(predicate: object, timeout: float = 1) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False


if __name__ == "__main__":
    unittest.main()
