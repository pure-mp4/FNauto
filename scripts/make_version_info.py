from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    sys.path.insert(0, str(ROOT))
    from version import APP_VERSION

    return APP_VERSION


APP_VERSION = _version()


def numeric_version(value: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in value.split(".")]
    if len(parts) != 3 or any(part < 0 for part in parts):
        raise ValueError(f"APP_VERSION must be MAJOR.MINOR.PATCH: {value!r}")
    return (*parts, 0)


def render(value: str) -> str:
    major, minor, patch, build = numeric_version(value)
    text = f"{major}.{minor}.{patch}.{build}"
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('FileDescription', 'FNauto'),
        StringStruct('FileVersion', '{text}'),
        StringStruct('InternalName', 'FNauto'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 FNauto contributors'),
        StringStruct('OriginalFilename', 'FNauto.exe'),
        StringStruct('ProductName', 'FNauto'),
        StringStruct('ProductVersion', '{text}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "version_info.txt"))
    args = parser.parse_args()
    Path(args.output).write_text(render(APP_VERSION), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
