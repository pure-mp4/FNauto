from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def source_path() -> str:
    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "assets" / "app_mark.png")
    candidates.append(Path(__file__).resolve().parent / "assets" / "app_mark.png")
    candidates.append(Path(sys.executable).resolve().parent / "assets" / "app_mark.png")
    for path in candidates:
        if path.is_file():
            return str(path)
    return ""


def pixmap(size: int) -> QPixmap:
    path = source_path()
    if path:
        source = QPixmap(path)
        if not source.isNull():
            return source.scaled(int(size), int(size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    empty = QPixmap(int(size), int(size))
    empty.fill(Qt.transparent)
    return empty


def icon() -> QIcon:
    out = QIcon()
    for size in SIZES:
        out.addPixmap(pixmap(size))
    return out
