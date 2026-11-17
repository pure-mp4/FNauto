import atexit
import ctypes
import time
from ctypes import wintypes
from typing import Callable, Optional, Tuple

VK_LBUTTON = 1
VK_RBUTTON = 2
SETTLE_S = 0.025
AFTER_S = 0.025
DRAG_WAIT_S = 0.5
WM_ACTIVATE, WM_KEYDOWN, WM_KEYUP, WA_ACTIVE = (6, 256, 257, 1)
VK_NAMES = {"space": 32, "esc": 27, "escape": 27, "w": 87, "a": 65, "s": 83, "d": 68, "enter": 13, "shift": 160, "shiftleft": 160}


class Win32Input:
    pass

    def __init__(self):
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        h, b = (wintypes.HANDLE, wintypes.BOOL)
        self.u.GetForegroundWindow.restype = h
        self.u.SetForegroundWindow.argtypes, self.u.SetForegroundWindow.restype = ([h], b)
        self.u.BringWindowToTop.argtypes, self.u.BringWindowToTop.restype = ([h], b)
        self.u.IsWindow.argtypes, self.u.IsWindow.restype = ([h], b)
        self.u.IsIconic.argtypes, self.u.IsIconic.restype = ([h], b)
        self.u.GetWindowThreadProcessId.argtypes = [h, ctypes.POINTER(wintypes.DWORD)]
        self.u.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.u.AttachThreadInput.argtypes, self.u.AttachThreadInput.restype = ([wintypes.DWORD, wintypes.DWORD, b], b)
        self.u.GetCursorPos.argtypes, self.u.GetCursorPos.restype = ([ctypes.POINTER(wintypes.POINT)], b)
        self.u.SetCursorPos.argtypes, self.u.SetCursorPos.restype = ([ctypes.c_int, ctypes.c_int], b)
        self.u.GetAsyncKeyState.argtypes, self.u.GetAsyncKeyState.restype = ([ctypes.c_int], ctypes.c_short)
        self.u.PostMessageW.argtypes, self.u.PostMessageW.restype = (
            [h, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
            b,
        )
        self.u.MapVirtualKeyW.argtypes, self.u.MapVirtualKeyW.restype = ([wintypes.UINT, wintypes.UINT], wintypes.UINT)
        self.k.GetCurrentThreadId.restype = wintypes.DWORD

    def foreground(self) -> Optional[int]:
        return self.u.GetForegroundWindow() or None

    def cursor_pos(self) -> Tuple[int, int]:
        pt = wintypes.POINT()
        self.u.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def set_cursor_pos(self, x: int, y: int) -> None:
        self.u.SetCursorPos(int(x), int(y))

    def button_down(self, vk: int) -> bool:
        return self.u.GetAsyncKeyState(vk) & 32768 != 0

    def is_window(self, hwnd) -> bool:
        return bool(self.u.IsWindow(hwnd))

    def is_iconic(self, hwnd) -> bool:
        return bool(self.u.IsIconic(hwnd))

    def force_foreground(self, hwnd) -> None:
        me = self.k.GetCurrentThreadId()
        fg = self.u.GetForegroundWindow()
        tids = {self.u.GetWindowThreadProcessId(w, None) for w in [fg, hwnd] if w}
        attached = [t for t in tids if t and t != me and self.u.AttachThreadInput(me, t, True)]
        try:
            self.u.BringWindowToTop(hwnd)
            self.u.SetForegroundWindow(hwnd)
        finally:
            for t in attached:
                self.u.AttachThreadInput(me, t, False)

    def post_key(self, hwnd, vk: int, down: bool) -> bool:
        scan = self.u.MapVirtualKeyW(vk, 0)
        self.u.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
        lparam = 1 | scan << 16 | (0 if down else 3221225472)
        return bool(self.u.PostMessageW(hwnd, WM_KEYDOWN if down else WM_KEYUP, vk, lparam))


class FocusSwapContext:
    pass

    def __init__(
        self,
        target_hwnd,
        api=None,
        settle_s: float = SETTLE_S,
        after_s: float = AFTER_S,
        drag_wait_s: float = DRAG_WAIT_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        kind: str = "key",
        point: Optional[Tuple[int, int]] = None,
        ghost=None,
        idle_ms: int = 1000,
        idle_wait_s: float = 5.0,
    ):
        self.target = target_hwnd
        self.api = api or Win32Input()
        self.settle_s, self.after_s, self.drag_wait_s = (settle_s, after_s, drag_wait_s)
        self._sleep, self._clock = (sleep, clock)
        self.kind, self.point, self.ghost = (kind, point, ghost)
        self.idle_ms, self.idle_wait_s = (idle_ms, idle_wait_s)
        self.prev_hwnd = None
        self.prev_cursor = None
        self.swapped = False
        self.did_swap = False
        self.click_blocked = False
        self._g = None
        self._own_open = False
        self._locked = False

    def _wait_for_user_drag(self) -> None:
        end = self._clock() + self.drag_wait_s
        while (self.api.button_down(VK_LBUTTON) or self.api.button_down(VK_RBUTTON)) and self._clock() < end:
            self._sleep(0.02)

    def _wait_for_idle(self) -> None:
        end = self._clock() + self.idle_wait_s
        while self._g.activity.idle_ms() < self.idle_ms and self._clock() < end:
            self._sleep(0.05)

    def __enter__(self):
        self.swapped = self.did_swap = self.click_blocked = False
        self._g = None
        self._locked = False
        try:
            api = self.api
            if not self.target or not api.is_window(self.target) or api.is_iconic(self.target):
                return self
            fg = api.foreground()
            if fg == self.target:
                return self
            if self.ghost and self.ghost.ensure():
                self._g = self.ghost
                self._wait_for_idle()
                self._g.activity.scan()
                self._g.activity.own_begin()
                self._own_open = True
                self._g.cap_lock.acquire()
                self._locked = True
                fg = api.foreground()
            self.prev_hwnd = fg
            self.prev_cursor = api.cursor_pos()
            self._wait_for_user_drag()
            self.swapped = self.did_swap = True
            if self._g:
                self._g.hide(self.kind == "click")
            api.force_foreground(self.target)
            self._sleep(self.settle_s)
            if self._g and self.kind == "click" and self.point:
                ga = self._g.api
                if ga.root_at(*self.point) != self.target:
                    ga.raise_top(self.target)
                    self.click_blocked = ga.root_at(*self.point) != self.target
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, _exc, tb) -> bool:
        api = self.api
        try:
            if self.swapped:
                try:
                    self._sleep(self.after_s)
                except Exception:
                    pass
                try:
                    if self._g:
                        self._g.sink()
                except Exception:
                    pass
                try:
                    if self.kind == "click" and self.prev_cursor is not None:
                        api.set_cursor_pos(*self.prev_cursor)
                except Exception:
                    pass
                prev = self.prev_hwnd
                try:
                    if prev and prev != self.target and api.is_window(prev):
                        api.force_foreground(prev)
                except Exception:
                    pass
                try:
                    if self._g:
                        self._g.rest()
                except Exception:
                    pass
        finally:
            if self._g and self._own_open:
                try:
                    self._g.activity.own_end()
                except Exception:
                    pass
            self._own_open = False
            if self._g and self._locked:
                self._g.cap_lock.release()
            self._locked = False
            self._g = None
            self.swapped = False
        return False


class BackgroundInput:
    pass

    def __init__(
        self,
        locator,
        settings,
        api=None,
        ghost=None,
        ghost_api=None,
        sleep=time.sleep,
        clock=time.monotonic,
        marker_path=None,
    ):
        self.locator, self.s = (locator, settings)
        self.api = api or Win32Input()
        self._sleep, self._clock = (sleep, clock)
        if ghost is None:
            from ghost import GhostApi, GhostWindow

            ghost = GhostWindow(api=ghost_api or GhostApi(), game_hwnd=locator.hwnd, marker_path=marker_path)
        self.ghost = ghost
        self._stop_registered = False
        self._noted = ""

    def _on(self) -> bool:
        return bool(getattr(self.s, "background_mode", False))

    def _ghost_on(self) -> bool:
        return (
            self._on()
            and bool(getattr(self.s, "background_ghost", True))
            and (not bool(getattr(self.s, "ghost_show", False)))
        )

    def sync(self) -> None:
        try:
            if self._ghost_on():
                self.ghost.ensure()
                return
            if self.ghost.hwnd:
                self.ghost.restore()
                return
        except Exception:
            pass

    def start(self) -> None:
        try:
            self.ghost.recover()
        except Exception:
            pass
        self.ghost.reset()
        self._noted = ""
        if not self._stop_registered:
            atexit.register(self.release_all)
            self._stop_registered = True
        self.sync()

    def release_all(self) -> None:
        try:
            self.ghost.restore()
        except Exception:
            return None

    def context(self, kind: str = "key", point: Optional[Tuple[int, int]] = None) -> FocusSwapContext:
        self.sync()
        return FocusSwapContext(
            self.locator.hwnd(),
            api=self.api,
            kind=kind,
            point=point,
            ghost=self.ghost if self._ghost_on() else None,
            sleep=self._sleep,
            clock=self._clock,
        )

    def other_window_in_front(self) -> bool:
        if not self._on():
            return False
        try:
            hwnd = self.locator.hwnd()
            fg = self.api.foreground()
            return bool(hwnd and fg and (fg != hwnd))
        except Exception:
            return False

    def user_busy(self, ms: int = 1500) -> bool:
        if not self._ghost_on():
            return False
        else:
            try:
                return self.ghost.activity.idle_ms() < ms
            except Exception:
                return False

    def watch(self, stop) -> None:
        self.ghost.watch(stop, self._ghost_on)

    def capture_guard(self):
        return self.ghost.cap_lock

    def ghost_notice(self, source: str = "window") -> str:
        try:
            if self.ghost.failed and self._ghost_on():
                key = "log_ghost_failed"
                if key != self._noted:
                    self._noted = key
                    return key
            return ""
        except Exception:
            return ""

    def post_key(self, key: str, down: bool) -> bool:
        vk, hwnd = (VK_NAMES.get(str(key).lower()), self.locator.hwnd())
        if not vk or not hwnd:
            return False
        else:
            try:
                return self.api.post_key(hwnd, vk, down)
            except Exception:
                return False

    def post_tap(self, key: str) -> bool:
        if not self.post_key(key, True):
            return False
        else:
            self._sleep(0.06)
            return self.post_key(key, False)
