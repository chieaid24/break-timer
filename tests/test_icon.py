from __future__ import annotations

import unittest

from PIL import ImageChops

from productivity_timer.windows import create_status_icon


class StatusIconTests(unittest.TestCase):
    def test_renders_supported_icon_sizes(self) -> None:
        for size in (16, 32, 48, 64, 128, 256):
            with self.subTest(size=size):
                icon = create_status_icon(True, size)

                self.assertEqual(icon.mode, "RGBA")
                self.assertEqual(icon.size, (size, size))
                self.assertEqual(icon.getpixel((0, 0))[3], 0)
                self.assertIsNotNone(icon.getbbox())

    def test_status_is_the_only_state_difference(self) -> None:
        running = create_status_icon(True, 256)
        paused = create_status_icon(False, 256)

        difference = ImageChops.difference(running, paused).convert("RGB")

        self.assertIsNotNone(difference.getbbox())
        self.assertEqual(running.getpixel((213, 213)), (46, 204, 113, 255))
        self.assertEqual(paused.getpixel((213, 213)), (231, 76, 60, 255))
        self.assertEqual(
            running.crop((0, 0, 180, 256)).tobytes(),
            paused.crop((0, 0, 180, 256)).tobytes(),
        )

    def test_rejects_non_positive_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "size must be positive"):
            create_status_icon(True, 0)

    def test_cigarette_ember_remains_visible_at_tray_size(self) -> None:
        icon = create_status_icon(True, 32)

        ember_pixels = sum(
            1
            for red, green, blue, alpha in icon.get_flattened_data()
            if red > 130 and green < 130 and blue < 100 and alpha > 150
        )

        self.assertGreaterEqual(ember_pixels, 3)


if __name__ == "__main__":
    unittest.main()
