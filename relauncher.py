import collections
import os
import subprocess
import threading
import time
from typing import Callable, Iterable, Optional, Set

GAME_EXE = "FortniteClient-Win64-Shipping.exe"
CLEAN_EXES = (GAME_EXE, "FortniteLauncher.exe", "CrashReportClient.exe")
EPIC_URI = "com.epicgames.launcher://apps/fn%3A4fe75bbc5a674f4f9b356b5c90567da5%3AFortnite?action=launch&silent=true"
POLL_S = 2.0
GONE_S = 15.0
HUNG_S = 90.0
MAX_AUTO_PER_HOUR = 3
WINDOW_S = 3600.0
MANUAL_GAP_S = 30.0
KILL_SETTLE_S = 4.0
LAUNCH_WAIT_S = 300.0
LIMIT_LOG_GAP_S = 600.0
PICTURE_STEP = 48
PICTURE_DELTA = 0.3
CREATE_NO_WINDOW = 134217728


def running_exes() -> Set[str]:
    from audio_mute import _process_names

    names = _process_names()
    if not names:
        raise OSError("empty process snapshot")
    else:
        return set(names.values())


def kill_exe(name: str, run: Callable = subprocess.run) -> bool:
    if name not in CLEAN_EXES:
        return False
    else:
        try:
            r = run(
                ["taskkill", "/F", "/T", "/IM", name], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15
            )
            return getattr(r, "returncode", 1) == 0
        except Exception:
            return False


def start_epic(uri: str = EPIC_URI, opener: Optional[Callable[[str], object]] = None) -> bool:
    try:
        (opener or os.startfile)(uri)
        return True
    except Exception:
        return False


def window_hung(hwnd: int) -> bool:
    try:
        if not hwnd:
            return False
        import ctypes

        return bool(ctypes.windll.user32.IsHungAppWindow(int(hwnd)))
    except Exception:
        return False


class GameRelauncher:
    def __init__(
        self,
        settings,
        log: Callable[[str], None] = lambda _m: None,
        procs: Callable[[], Iterable[str]] = running_exes,
        killer: Callable[[str], bool] = kill_exe,
        opener: Callable[[], bool] = start_epic,
        hung: Optional[Callable[[], bool]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Optional[Callable[[float], object]] = None,
    ):
        self.s = settings
        self.log = log
        self._procs, self._kill, self._open, self._hung = (procs, killer, opener, hung)
        self._clock = clock
        self._sleep = sleeper
        self.seen = False
        self.phase = "idle"
        self.count = 0
        self._gone_since = None
        self._hung_since = None
        self._alive_at = None
        self._prev_pic = None
        self._hung_noted = False
        self._auto_times = collections.deque()
        self._last_manual = -1000000000.0
        self._limit_logged = -1000000000.0
        self._req = None
        self._reset = False
        self._lobby = threading.Event()
        self._busy = threading.Lock()
        self._stop = threading.Event()

    def note_play(self) -> None:
        self._lobby.set()

    def pop_reset(self) -> bool:
        r, self._reset = (self._reset, False)
        return r

    def request(self, reason: str = "manual") -> bool:
        if self.phase != "idle" or self._req is not None:
            return False
        else:
            if reason == "manual" and self._clock() - self._last_manual < MANUAL_GAP_S:
                return False
            else:
                self._req = reason
                return True

    def allowed_auto(self) -> bool:
        now = self._clock()
        while self._auto_times and now - self._auto_times[0] >= WINDOW_S:
            self._auto_times.popleft()
        return len(self._auto_times) < MAX_AUTO_PER_HOUR

    def note_step(self, frame=None, clicked: bool = False) -> None:
        try:
            if clicked:
                self._alive_at = self._clock()
            if frame is not None:
                small = frame[::PICTURE_STEP, ::PICTURE_STEP].astype("int16")
                prev, self._prev_pic = (self._prev_pic, small)
                if prev is None or prev.shape != small.shape or float(abs(small - prev).mean()) >= PICTURE_DELTA:
                    self._alive_at = self._clock()
        except Exception:
            return None

    def check(self, freeze: bool = True) -> Optional[str]:
        try:
            now = self._clock()
            alive = GAME_EXE.lower() in {str(n).lower() for n in self._procs()}
            if alive:
                self.seen = True
                self._gone_since = None
                if freeze and self._hung is not None and self._hung():
                    if self._hung_since is None:
                        self._hung_since = now
                        self._hung_noted = False
                    if now - self._hung_since >= HUNG_S:
                        if self._alive_at is None or now - self._alive_at >= HUNG_S:
                            return "freeze"
                        if not self._hung_noted:
                            self._hung_noted = True
                            self.log(
                                "[relaunch] game window not responding, but the picture is still moving: not treated as a freeze"
                            )
                    return None
                self._hung_since = None
                return None
            self._hung_since = None
            if not self.seen or self.phase != "idle":
                return None
            if self._gone_since is None:
                self._gone_since = now
            return "crash" if now - self._gone_since >= GONE_S else None
        except Exception:
            return None

    def _wait(self, seconds: float) -> bool:
        if self._sleep is not None:
            self._sleep(seconds)
            return self._stop.is_set()
        else:
            return self._stop.wait(seconds)

    def relaunch(self, reason: str = "manual", wait_lobby: bool = True) -> bool:
        if not self._busy.acquire(blocking=False):
            return False
        try:
            auto = reason in ("crash", "freeze")
            now = self._clock()
            if auto:
                self._auto_times.append(now)
            else:
                self._last_manual = now
            self._lobby.clear()
            self.phase = "cleaning"
            self.log(f"[relaunch] {reason}: closing what is left of Fortnite")
            try:
                present = {str(n).lower() for n in self._procs()}
            except Exception:
                present = set()
            for exe in CLEAN_EXES:
                if exe.lower() in present:
                    try:
                        self._kill(exe)
                    except Exception:
                        pass
            try:
                if self._wait(KILL_SETTLE_S):
                    return False
                self.phase = "launching"
                if not self._open():
                    self.log("[relaunch] could not start the Epic Games Launcher address (is the launcher installed?)")
                    self.seen = False
                    return False
                self.count += 1
                self._reset = True
                self._gone_since = self._hung_since = None
                self.seen = False
                self.phase = "waiting"
                self.log(
                    f"[relaunch] game started (#{self.count}); waiting for the lobby (up to {LAUNCH_WAIT_S:.0f} s)"
                )
                up = False
                t_end = self._clock() + LAUNCH_WAIT_S
                while self._clock() < t_end:
                    if self._wait(1.0):
                        return up
                    if GAME_EXE.lower() in {str(n).lower() for n in self._procs()}:
                        if not up:
                            up = True
                            self.seen = True
                            self.log("[relaunch] game process is up")
                        if not wait_lobby:
                            return True
                    try:
                        if wait_lobby and self._lobby.is_set():
                            self.log("[relaunch] back in the lobby")
                            return True
                    except Exception:
                        pass
                self.log(
                    f"[relaunch] the lobby was not reached within {LAUNCH_WAIT_S:.0f} s"
                    if up
                    else "[relaunch] the game did not start"
                )
                return up and (not wait_lobby)
            finally:
                self.phase = "idle"
                self._busy.release()
        except Exception as e:
            self.log(f"[relaunch] error: {type(e).__name__}")
            self.phase = "idle"
            self._busy.release()
            return False

    def run(self, stop: threading.Event) -> None:
        self._stop = stop
        while not stop.wait(POLL_S):
            try:
                req, self._req = (self._req, None)
                if req:
                    self.relaunch(req)
                    continue
                auto_on = bool(getattr(self.s, "auto_relaunch_enabled", True))
                reason = self.check(freeze=auto_on and bool(getattr(self.s, "auto_relaunch_freeze_enabled", True)))
                if reason is None or not auto_on:
                    continue
                if not self.allowed_auto():
                    now = self._clock()
                    if now - self._limit_logged >= LIMIT_LOG_GAP_S:
                        self._limit_logged = now
                        self.log(
                            f"[relaunch] {MAX_AUTO_PER_HOUR} automatic relaunches in the last hour: not restarting again for now"
                        )
                    continue
                self.relaunch(reason)
            except Exception as e:
                self.log(f"[relaunch] error: {type(e).__name__}")


def manual_relaunch(settings, log: Callable[[str], None] = lambda _m: None, **kw) -> threading.Thread:
    r = GameRelauncher(settings, log=log, **kw)
    t = threading.Thread(target=lambda: r.relaunch("manual", wait_lobby=False), daemon=True, name="FNauto-relaunch")
    t.start()
    return t
