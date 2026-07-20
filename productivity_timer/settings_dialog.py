"""Native settings window for the Windows tray application."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from productivity_timer.settings import (
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    NotificationSound,
    ReminderSettings,
)

SOUND_CHOICES = {
    "Windows default": NotificationSound.DEFAULT,
    "Reminder": NotificationSound.REMINDER,
    "Mail": NotificationSound.MAIL,
    "Instant message": NotificationSound.INSTANT_MESSAGE,
    "Text message": NotificationSound.TEXT_MESSAGE,
    "Silent": NotificationSound.SILENT,
    "Custom WAV": NotificationSound.CUSTOM,
}
SOUND_LABELS = {sound: label for label, sound in SOUND_CHOICES.items()}


def settings_from_values(
    interval: str,
    message: str,
    sound_label: str,
    custom_sound: str,
) -> ReminderSettings:
    """Validate settings window values."""
    try:
        interval_minutes = int(interval)
    except ValueError as error:
        raise ValueError("Interval must be a whole number.") from error

    try:
        sound = SOUND_CHOICES[sound_label]
    except KeyError as error:
        raise ValueError("Choose a listed sound.") from error

    custom_path = Path(custom_sound) if custom_sound else None
    if sound is NotificationSound.CUSTOM and (
        custom_path is None or not custom_path.is_file()
    ):
        raise ValueError("Choose an existing custom WAV file.")

    return ReminderSettings(
        interval_minutes=interval_minutes,
        message=message.strip(),
        sound=sound,
        custom_sound=custom_path,
    )


class SettingsDialog:
    """Open at most one non-blocking Tk settings window."""

    def __init__(self, icon_path: Path | None = None) -> None:
        self._icon_path = icon_path
        self._lock = threading.Lock()
        self._is_open = False

    def open(
        self,
        settings: ReminderSettings,
        on_save: Callable[[ReminderSettings], None],
    ) -> None:
        with self._lock:
            if self._is_open:
                return
            self._is_open = True
        threading.Thread(
            target=self._run,
            args=(settings, on_save),
            name="settings-window",
            daemon=True,
        ).start()

    def _run(
        self,
        settings: ReminderSettings,
        on_save: Callable[[ReminderSettings], None],
    ) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        try:
            root = tk.Tk()
            root.title("Productivity Timer settings")
            root.resizable(False, False)
            if self._icon_path is not None:
                with suppress(tk.TclError):
                    root.iconbitmap(default=str(self._icon_path))

            frame = ttk.Frame(root, padding=16)
            frame.grid(sticky="nsew")
            frame.columnconfigure(1, weight=1)

            ttk.Label(frame, text="Break interval").grid(
                row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
            )
            interval_value = tk.StringVar(value=str(settings.interval_minutes))
            interval = ttk.Spinbox(
                frame,
                from_=MIN_INTERVAL_MINUTES,
                to=MAX_INTERVAL_MINUTES,
                textvariable=interval_value,
                width=7,
            )
            interval.grid(row=0, column=1, sticky="w", pady=(0, 10))
            ttk.Label(frame, text="minutes").grid(
                row=0, column=2, sticky="w", padx=(6, 0), pady=(0, 10)
            )

            ttk.Label(frame, text="Message").grid(
                row=1, column=0, sticky="nw", padx=(0, 12), pady=(0, 10)
            )
            message = tk.Text(frame, width=38, height=4, wrap="word")
            message.insert("1.0", settings.message)
            message.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 10))

            ttk.Label(frame, text="Sound").grid(
                row=2, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
            )
            sound_value = tk.StringVar(value=SOUND_LABELS[settings.sound])
            sound = ttk.Combobox(
                frame,
                values=tuple(SOUND_CHOICES),
                textvariable=sound_value,
                state="readonly",
                width=22,
            )
            sound.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 10))

            custom_value = tk.StringVar(
                value=str(settings.custom_sound) if settings.custom_sound else ""
            )
            custom_label = ttk.Label(frame, text="WAV file")
            custom_path = ttk.Entry(
                frame,
                textvariable=custom_value,
                state="readonly",
                width=28,
            )
            browse = ttk.Button(
                frame,
                text="Browse...",
                command=lambda: self._browse_wav(
                    root,
                    custom_value,
                    filedialog.askopenfilename,
                ),
            )

            def update_custom_fields(*args: object) -> None:
                if sound_value.get() == "Custom WAV":
                    custom_label.grid(
                        row=3, column=0, sticky="w", padx=(0, 12), pady=(0, 14)
                    )
                    custom_path.grid(row=3, column=1, sticky="ew", pady=(0, 14))
                    browse.grid(row=3, column=2, sticky="e", padx=(6, 0), pady=(0, 14))
                else:
                    custom_label.grid_remove()
                    custom_path.grid_remove()
                    browse.grid_remove()

            sound_value.trace_add("write", update_custom_fields)
            update_custom_fields()

            actions = ttk.Frame(frame)
            actions.grid(row=4, column=0, columnspan=3, sticky="e")

            def save(*args: object) -> None:
                try:
                    updated = settings_from_values(
                        interval_value.get(),
                        message.get("1.0", "end-1c"),
                        sound_value.get(),
                        custom_value.get(),
                    )
                    on_save(updated)
                except (OSError, ValueError) as error:
                    messagebox.showerror(
                        "Could not save settings",
                        str(error),
                        parent=root,
                    )
                    return
                root.destroy()

            ttk.Button(actions, text="Save", command=save, default="active").grid(
                row=0, column=0, padx=(0, 8)
            )
            ttk.Button(actions, text="Cancel", command=root.destroy).grid(
                row=0, column=1
            )

            root.bind("<Escape>", lambda event: root.destroy())
            root.bind("<Control-Return>", save)
            root.protocol("WM_DELETE_WINDOW", root.destroy)
            root.update_idletasks()
            left = max(0, (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2)
            top = max(0, (root.winfo_screenheight() - root.winfo_reqheight()) // 2)
            root.geometry(f"+{left}+{top}")
            root.lift()
            root.attributes("-topmost", True)
            root.after_idle(root.attributes, "-topmost", False)
            interval.focus_set()
            root.mainloop()
        finally:
            with self._lock:
                self._is_open = False

    @staticmethod
    def _browse_wav(
        root: object,
        custom_value: object,
        askopenfilename: Callable[..., str],
    ) -> None:
        selected = askopenfilename(
            parent=root,
            title="Choose a notification sound",
            filetypes=(("WAV audio", "*.wav"),),
        )
        if selected:
            custom_value.set(selected)
