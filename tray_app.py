import threading
import time
from datetime import datetime
from typing import Callable

from PIL import Image, ImageDraw
from winotify import Notification  # still unused but kept to preserve your logic
from windows_toasts import Toast, ToastDisplayImage, WindowsToaster
import pystray


DEFAULT_MINUTES = 20
DEFAULT_MESSAGE = "Stretch, Rest Eyes, Water, and Walk!"


# ---------------------- ICON FACTORY ----------------------
def create_status_icon(is_running: bool) -> Image.Image:
    """Generate a small tray icon indicating running/stopped state."""
    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse((4, 4, 60, 60), fill=(30, 30, 30, 255))

    color = (46, 204, 113, 255) if is_running else (231, 76, 60, 255)
    draw.ellipse((40, 40, 60, 60), fill=color)

    draw.text((14, 18), "PT", fill=(240, 240, 240, 255))
    return img


# ---------------------- ORIGINAL TOAST SYSTEM ----------------------
def build_notification() -> None:
    """Create and display a Windows toast using windows_toasts."""
    toaster = WindowsToaster("Productivity Reminder")
    newToast = Toast()
    newToast.text_fields = [DEFAULT_MESSAGE]
    newToast.on_activated = lambda _: print("Toast clicked!")
    toaster.show_toast(newToast)
    print(f"Toast shown at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return None


# ---------------------- MAIN APP ----------------------
class ReminderApp:
    def __init__(self, interval_minutes: int):
        self.interval_seconds = interval_minutes * 60
        self.running = threading.Event()
        self.shutdown = threading.Event()
        self.toast_factory: Callable[[], None] = build_notification

        self.icon = pystray.Icon("productivity_timer")
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)

    def run(self) -> None:
        self.worker.start()

        self.icon.icon = create_status_icon(is_running=False)
        self.icon.menu = pystray.Menu(
            pystray.MenuItem("Start", self.start, default=True),
            pystray.MenuItem("Stop", self.stop),
            pystray.MenuItem("Quit", self.quit)
        )
        self.icon.run()

    # ---------------------- Tray Actions ----------------------
    def start(self, icon=None, item=None) -> None:
        self.running.set()
        self._update_icon(True)

    def stop(self, icon=None, item=None) -> None:
        self.running.clear()
        self._update_icon(False)

    def quit(self, icon=None, item=None) -> None:
        self.running.clear()
        self.shutdown.set()
        self.icon.stop()

    # ---------------------- Update Icon ----------------------
    def _update_icon(self, is_running: bool) -> None:
        self.icon.icon = create_status_icon(is_running)

        # IMPORTANT: update_icon() is required for tray redraw
        if self.icon.visible:
            self.icon.update_icon()
            self.icon.update_menu()

    # ---------------------- Worker Thread ----------------------
    def _worker_loop(self) -> None:
        while not self.shutdown.is_set():
            if not self.running.is_set():
                time.sleep(0.5)
                continue

            remaining = self.interval_seconds

            while (
                remaining > 0
                and not self.shutdown.is_set()
                and self.running.is_set()
            ):
                time.sleep(1)
                remaining -= 1

            # If stopped or quitting, don't fire
            if self.shutdown.is_set() or not self.running.is_set():
                continue

            # FIRE YOUR ORIGINAL NOTIFICATION HERE
            self.toast_factory()


# ---------------------- Entry point ----------------------
if __name__ == "__main__":
    # Removed input() (breaks packaged apps)
    interval = DEFAULT_MINUTES

    app = ReminderApp(interval_minutes=interval)
    app.run()
