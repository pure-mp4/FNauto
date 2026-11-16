import ctypes
import os
import sys
import tempfile
import time
from typing import List

import config
import focus
import window_capture as wc
from version import APP_VERSION


def _admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _variant_name(flags: int) -> str:
    if flags & wc.PW_RENDERFULLCONTENT:
        return "PW_RENDERFULLCONTENT|PW_CLIENTONLY"
    return "PW_CLIENTONLY"


def build_report(api=None, gdi=None) -> List[str]:
    api = api or focus.WinApi()
    gdi = gdi or wc.Win32Gdi()
    lines = [
        f"FNauto {APP_VERSION} | frozen={bool(getattr(sys, 'frozen', False))} | "
        f"this program runs as administrator: {_admin()}"
    ]
    try:
        windows = api.windows()
    except Exception as error:
        return lines + [f"cannot list windows: {error}"]
    related = []
    for handle in windows:
        cls, title = api.class_name(handle), api.title(handle)
        low = (cls + " " + title).lower()
        if cls == focus.GAME_CLASS or any(k in low for k in ("fortnite", "geforce now", "フォートナイト")):
            related.append((handle, cls, title))
    lines.append(f"windows that look related to the game: {len(related)}")
    for handle, cls, title in related:
        try:
            process = api.process_name(handle)
        except Exception:
            process = ""
        rect = gdi.client_rect(handle)
        lines.append(
            f"  hwnd={handle} class={cls!r} title={title!r} program={process!r} "
            f"client={rect[2]}x{(rect[3] if rect else '?')} minimized={gdi.is_iconic(handle)}"
        )
    game = focus.find_game(api)
    if not game:
        lines.append(
            "RESULT: the game window was NOT found (start the game first; if it is running, send this report)."
        )
        return lines
    lines.append(f"game window found: hwnd={game}, class={api.class_name(game)!r}, title={api.title(game)!r}")
    if gdi.is_iconic(game):
        lines.append(
            "RESULT: the game window is minimized - Windows does not draw it, so it cannot be captured. "
            "Un-minimize it and set the display mode to Windowed Fullscreen."
        )
        return lines
    rect = gdi.client_rect(game)
    if not rect or rect[2] <= 0 or rect[3] <= 0:
        lines.append(f"RESULT: the window has no usable client area ({rect}).")
        return lines
    left, top, width, height = rect
    lines.append(f"client area: {width}x{height} at screen position ({left}, {top})")
    capture = wc.WindowCapture(wc.GameWindow(finder=lambda: game, is_window=gdi.is_window), api=gdi)
    working = None
    for flags in wc.FLAG_VARIANTS:
        started = time.perf_counter()
        capture._denied = False
        frame = capture._print(game, width, height, flags)
        milliseconds = (time.perf_counter() - started) * 1000
        if frame is None:
            why = (
                "ACCESS DENIED (the game runs as administrator; run FNauto as administrator)"
                if capture._denied
                else "failed"
            )
            lines.append(f"  PrintWindow {_variant_name(flags)}: {why} [{milliseconds:.0f} ms]")
            if capture._denied:
                break
        elif wc._is_black(frame):
            lines.append(f"  PrintWindow {_variant_name(flags)}: BLACK picture [{milliseconds:.0f} ms]")
        else:
            lines.append(
                f"  PrintWindow {_variant_name(flags)}: OK, mean brightness "
                f"{float(frame.mean()):.0f} [{milliseconds:.0f} ms]"
            )
            working = working or flags
    if working is not None:
        lines.append("RESULT: the game window can be captured, also behind other windows. Background mode should work.")
    else:
        lines.append(
            "RESULT: the game window cannot be captured behind other windows with this method. "
            "Keep the game uncovered (FNauto then falls back to the normal screen capture), or send this report."
        )
    return lines


REPORT_NAME = "FNauto_report.txt"


def default_report_path() -> str:
    for folder in (config.base_dir(), os.path.join(os.path.expanduser("~"), "Desktop"), tempfile.gettempdir()):
        try:
            if os.path.isdir(folder) and os.access(folder, os.W_OK):
                return os.path.join(folder, REPORT_NAME)
        except Exception:
            pass
    return os.path.join(tempfile.gettempdir(), REPORT_NAME)


def run(out_path: str) -> None:
    try:
        lines = build_report()
    except Exception as error:
        lines = [f"diagnose failed: {type(error).__name__}: {error}"]
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
