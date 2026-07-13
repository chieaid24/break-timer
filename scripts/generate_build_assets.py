"""Generate version metadata and the Windows application icon."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from productivity_timer import APP_NAME, __version__  # noqa: E402
from productivity_timer.windows import create_status_icon  # noqa: E402

ASSET_DIR = ROOT / ".build-assets"


def main() -> None:
    version = tuple(int(part) for part in __version__.split("."))
    if len(version) != 3:
        raise ValueError("__version__ must contain three numeric parts")

    ASSET_DIR.mkdir(exist_ok=True)
    create_status_icon(True, 256).save(
        ASSET_DIR / "ProductivityTimer.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    version_quad = (*version, 0)
    (ASSET_DIR / "version_info.txt").write_text(
        _version_info(version_quad),
        encoding="ascii",
    )


def _version_info(version: tuple[int, int, int, int]) -> str:
    version_text = ".".join(str(part) for part in version[:3])
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version},
    prodvers={version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'Productivity Timer'),
          StringStruct(u'FileDescription', u'{APP_NAME}'),
          StringStruct(u'FileVersion', u'{version_text}'),
          StringStruct(u'InternalName', u'ProductivityTimer'),
          StringStruct(u'OriginalFilename', u'ProductivityTimer.exe'),
          StringStruct(u'ProductName', u'{APP_NAME}'),
          StringStruct(u'ProductVersion', u'{version_text}'),
        ],
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])]),
  ],
)
"""


if __name__ == "__main__":
    main()
