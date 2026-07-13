"""Thread-safe reminder scheduling."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    """A coherent view of the reminder schedule."""

    running: bool
    last_triggered: datetime | None
    next_trigger: datetime | None


class ReminderTimer:
    """Own the reminder thread and hide its lifecycle and timing details."""

    def __init__(
        self,
        interval: timedelta,
        notify: Callable[[], None],
        *,
        last_triggered: datetime | None = None,
        on_change: Callable[[TimerSnapshot], None] | None = None,
    ) -> None:
        if interval <= timedelta(0):
            raise ValueError("interval must be positive")

        self._interval = interval
        self._interval_seconds = interval.total_seconds()
        self._notify = notify
        self._on_change = on_change
        self._condition = threading.Condition()
        self._running = False
        self._closed = False
        self._last_triggered = last_triggered
        self._next_trigger: datetime | None = None
        self._deadline: float | None = None
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="reminder-timer",
            daemon=True,
        )
        self._worker.start()

    @property
    def snapshot(self) -> TimerSnapshot:
        with self._condition:
            return self._snapshot_locked()

    def start(self) -> None:
        """Start a fresh interval, or do nothing when already running."""
        with self._condition:
            if self._closed:
                raise RuntimeError("timer is shut down")
            if self._running:
                return
            self._running = True
            self._schedule_locked()
            snapshot = self._snapshot_locked()
            self._condition.notify_all()
        self._emit(snapshot)

    def pause(self) -> None:
        """Pause for this process and discard the current interval."""
        with self._condition:
            if self._closed or not self._running:
                return
            self._running = False
            self._deadline = None
            self._next_trigger = None
            snapshot = self._snapshot_locked()
            self._condition.notify_all()
        self._emit(snapshot)

    def shutdown(self) -> None:
        """Stop the worker permanently. This operation is idempotent."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._running = False
            self._deadline = None
            self._next_trigger = None
            snapshot = self._snapshot_locked()
            self._condition.notify_all()
        self._emit(snapshot)
        if threading.current_thread() is not self._worker:
            self._worker.join()

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._closed and self._deadline is None:
                    self._condition.wait()
                if self._closed:
                    return

                remaining = self._deadline - time.monotonic()
                if remaining > 0:
                    self._condition.wait(remaining)
                    continue

                self._deadline = None

            triggered_at: datetime | None = None
            try:
                self._notify()
            except Exception:
                logger.exception("Reminder notification failed")
            else:
                triggered_at = _local_now()

            with self._condition:
                if triggered_at is not None:
                    self._last_triggered = triggered_at
                if self._running and not self._closed:
                    self._schedule_locked()
                else:
                    self._next_trigger = None
                snapshot = self._snapshot_locked()
                self._condition.notify_all()
            self._emit(snapshot)

    def _schedule_locked(self) -> None:
        self._deadline = time.monotonic() + self._interval_seconds
        self._next_trigger = _local_now() + self._interval

    def _snapshot_locked(self) -> TimerSnapshot:
        return TimerSnapshot(
            running=self._running,
            last_triggered=self._last_triggered,
            next_trigger=self._next_trigger,
        )

    def _emit(self, snapshot: TimerSnapshot) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(snapshot)
        except Exception:
            logger.exception("Reminder state update failed")


def _local_now() -> datetime:
    return datetime.now().astimezone()
