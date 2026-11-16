from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import traceback

import config
from redact import redact

ERROR_ALREADY_EXISTS = 183


def first_run(path: str = "") -> bool:
    if not path:
        config.migrate_legacy_settings()
    return not os.path.exists(path or config.user_settings_path())


def clamp_geometry(x: int, y: int, w: int, h: int, screen: tuple) -> tuple:
    sx, sy, sw, sh = (int(v) for v in screen)
    w, h = int(w), int(h)
    x = max(sx, min(int(x), sx + sw - w))
    y = max(sy, min(int(y), sy + sh - h))
    return (x, y)


def window_position(saved_x, saved_y, w: int, h: int, screen: tuple) -> tuple:
    sx, sy, sw, sh = (int(v) for v in screen)
    x, y = int(saved_x), int(saved_y)
    if (x, y) == (-1, -1):
        x, y = sx + (sw - int(w)) // 2, sy + max(0, (sh - int(h)) // 3)
    return clamp_geometry(x, y, w, h, screen)


class InstanceGuard:
    def __init__(self, name: str = "FNauto.FNauto.1"):
        self.name = name
        self.handle = None

    def acquire(self) -> bool:
        if self.handle:
            return True
        try:
            k = ctypes.windll.kernel32
            self.handle = k.CreateMutexW(None, False, self.name)
            return bool(self.handle) and k.GetLastError() != ERROR_ALREADY_EXISTS
        except Exception:
            self.handle = None
            return True

    def release(self) -> None:
        if not self.handle:
            return
        try:
            ctypes.windll.kernel32.CloseHandle(self.handle)
        except Exception:
            pass
        self.handle = None


class FileLogger:
    def __init__(self, path: str = "", max_bytes: int = 1_000_000):
        self.path = path or os.path.join(config.base_dir(), "FNauto.log")
        self.max_bytes = int(max_bytes)
        self._lock = threading.Lock()

    def write(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {redact(message)}\n"
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                try:
                    if os.path.getsize(self.path) >= self.max_bytes:
                        os.replace(self.path, self.path + ".1")
                except OSError:
                    pass
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                return


def _error_component(tb, fallback: str = "the application") -> str:
    frame = tb
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if frame is None:
        return fallback
    module = str(frame.tb_frame.f_globals.get("__name__") or fallback)
    name = str(getattr(frame.tb_frame.f_code, "co_name", "") or "unknown")
    return f"{module}.{name}"


def _report_exception(logger: FileLogger, notify, kind, value, tb, component: str) -> None:
    text = "".join(traceback.format_exception(kind, value, tb))
    logger.write(text.rstrip())
    reason = redact(str(value).splitlines()[0][:180] if str(value) else kind.__name__)
    if notify is not None:
        try:
            notify(f"Something went wrong in {component}: {kind.__name__}: {reason}")
        except Exception:
            pass


def install_excepthook(logger: FileLogger, notify=None):
    old = sys.excepthook

    def hook(kind, value, tb):
        try:
            _report_exception(logger, notify, kind, value, tb, _error_component(tb))
        except Exception:
            pass

    def thread_hook(args):
        try:
            thread = getattr(args, "thread", None)
            name = getattr(thread, "name", "") or "worker thread"
            _report_exception(
                logger,
                notify,
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                f"{name} ({_error_component(args.exc_traceback, name)})",
            )
        except Exception:
            pass

    sys.excepthook = hook
    threading.excepthook = thread_hook
    return old


def taskbar_icon_path() -> str:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), "icon.ico"))
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "icon.ico"))
    candidates.append(os.path.join(config.base_dir(), "icon.ico"))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def apply_taskbar_icon(hwnd: int, path: str = "") -> list:
    if os.name != "nt" or not hwnd:
        return []
    path = path or taskbar_icon_path()
    if not path:
        return []
    try:
        user32 = ctypes.windll.user32
        load = user32.LoadImageW
        load.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        load.restype = ctypes.c_void_p
        send = user32.SendMessageW
        send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        send.restype = ctypes.c_void_p
        handles = []
        for size, which in ((32, 1), (16, 0)):
            icon = load(None, path, 1, size, size, 0x10)
            if icon:
                send(int(hwnd), 0x80, which, icon)
                handles.append(icon)
        return handles
    except Exception:
        return []


def ghost_recovery(path: str = "") -> bool:
    try:
        import ghost

        return bool(ghost.recover_at_launch(path or os.path.join(config.base_dir(), ghost.MARKER_NAME)))
    except Exception:
        return False


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, ""
        else:
            exe = sys.executable
            args = " ".join([os.path.abspath(sys.argv[0])] + sys.argv[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, os.getcwd(), 1)
        return int(rc) > 32
    except Exception:
        return False


def selftest_report(path: str) -> str:
    lines = []
    from version import APP_VERSION

    lines.append(f"version: {APP_VERSION}")
    for mod in (
        "PySide6",
        "cv2",
        "numpy",
        "mss",
        "keyboard",
        "PIL.Image",
        "qr",
        "web_remote",
        "updater",
        "ghost",
        "window_capture",
    ):
        try:
            __import__(mod)
            lines.append(f"import {mod}: ok")
        except Exception as e:
            lines.append(f"import {mod}: FAIL {e}")
    try:
        import i18n

        for lang in config.LANGS:
            ok = len(i18n.guide(lang)) == len(i18n.guide("en"))
            lines.append(f"i18n {lang}: {('ok' if ok else 'FAIL')}")
    except Exception as e:
        lines.append(f"i18n: FAIL {e}")
    try:
        from version import APP_VERSION
        from updater import is_newer

        lines.append(
            f"updater: {('ok' if is_newer('v99', APP_VERSION) and not is_newer('v0.1', APP_VERSION) else 'FAIL')}"
        )
    except Exception as e:
        lines.append(f"updater: FAIL {e}")
    try:
        from discord_webhook import DiscordReporter

        class _Probe:
            discord_webhook_url = ""

        reporter = DiscordReporter(_Probe(), sync=True)
        reporter.begin_session()
        reporter.record_action()
        lines.append(f"discord webhook: ok actions={reporter.snapshot()['total_actions']}")
    except Exception as e:
        lines.append(f"discord webhook: FAIL {e}")
    try:
        import worker

        templates = worker.load_templates("en")
        missing = sorted(
            k
            for k, v in templates.items()
            if v is None and config.uses_template(k, "en") and k not in config.OPTIONAL_TEMPLATES
        )
        lines.append(f"templates: {('ok' if not missing else 'FAIL')} {len(templates)} ({','.join(missing)})")
        from vision import capture_for_matching

        lines.append(f"capture: {'ok' if callable(capture_for_matching) else 'FAIL'}")
        from focus import ensure_game_foreground

        lines.append(f"focus: {'ok' if callable(ensure_game_foreground) else 'FAIL'}")
    except Exception as e:
        lines.append(f"templates: FAIL {e}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return "\n".join(lines)
