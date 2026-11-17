import contextlib
import random
import threading
import time
from typing import Callable, Optional
import i18n
import humanizer

MOUSEEVENTF_MOVE = 1


def _mouse_event_move(dx: int, dy: int) -> None:
    import ctypes

    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


def move_camera_smooth(
    dx: int,
    dy: int,
    duration_ms: int,
    mover: Optional[Callable[[int, int], None]] = None,
    sleeper=time.sleep,
    rng: Optional[random.Random] = None,
) -> int:
    mover = mover or _mouse_event_move
    steps = humanizer.camera_steps(int(dx), int(dy), int(duration_ms), rng or random.Random())
    for sx, sy, delay in steps:
        if sx or sy:
            mover(sx, sy)
        sleeper(delay)
    return len(steps)


def _cursor_pos():
    import ctypes
    from ctypes import wintypes

    pt = wintypes.POINT()
    return (pt.x, pt.y) if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)) else None


class Controller:
    def __init__(
        self,
        settings,
        clicker: Optional[Callable[[int, int], None]] = None,
        sleeper=time.sleep,
        clock=time.monotonic,
        presser: Optional[Callable[[str], None]] = None,
        focuser: Optional[Callable[[], object]] = None,
        swapper: Optional[Callable[..., object]] = None,
        poster: Optional[Callable[[str], bool]] = None,
        mover: Optional[Callable[[int, int], None]] = None,
        swinger: Optional[Callable[[int, int, float], None]] = None,
        cursor: Optional[Callable[[], object]] = None,
        rng: Optional[random.Random] = None,
        away: Optional[Callable[[], bool]] = None,
    ):
        self.s = settings
        self._clicker = clicker or self._default_click
        self._presser = presser or self._default_press
        self._focuser = focuser
        self._swapper = swapper
        self._poster = poster
        self._mover = mover
        self._swinger = swinger or self._default_swing
        self._cursor = cursor or _cursor_pos
        self._rng = rng or random.Random()
        self._away = away
        self._sleep = sleeper
        self._clock = clock
        self._last_click = -1000000000.0

    def _background(self) -> bool:
        return bool(self._swapper and getattr(self.s, "background_mode", False))

    def _input_context(self, kind: str = "key", point=None):
        if self._background():
            return self._swapper(kind, point)
        else:
            return contextlib.nullcontext()

    def _humanize(self) -> bool:
        return bool(getattr(self.s, "humanizer_enabled", False))

    def _default_click(self, x: int, y: int) -> None:
        import pydirectinput

        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        if self._humanize():
            r = self._rng
            start = (x - r.randint(8, 16), y - r.randint(4, 8))
            bg = self._background()
            n = 2 if bg else r.randint(3, 6)
            total = 0.015 if bg else r.uniform(0.015, 0.04)
            pydirectinput.moveTo(*start)
            for px, py in humanizer.bezier_points(start, (x, y), n, r):
                pydirectinput.moveTo(px, py)
                time.sleep(total / n)
            time.sleep(r.uniform(0.02, 0.05) if bg else r.uniform(0.06, 0.12))
            pydirectinput.mouseDown(button="left")
            time.sleep(humanizer.click_hold(r))
            pydirectinput.mouseUp(button="left")
        else:
            pydirectinput.moveTo(x - random.randint(8, 16), y - random.randint(4, 8))
            time.sleep(random.uniform(0.04, 0.08))
            pydirectinput.moveTo(x, y)
            time.sleep(random.uniform(0.1, 0.2))
            pydirectinput.mouseDown(button="left")
            time.sleep(random.uniform(0.06, 0.12))
            pydirectinput.mouseUp(button="left")

    @staticmethod
    def _default_swing(x: int, y: int, hold: float) -> None:
        import pydirectinput

        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        pydirectinput.moveTo(x, y)
        pydirectinput.mouseDown(button="left")
        time.sleep(hold)
        pydirectinput.mouseUp(button="left")

    @staticmethod
    def _default_press(key: str) -> None:
        import pydirectinput

        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        pydirectinput.keyDown(key)
        time.sleep(random.uniform(0.06, 0.12))
        pydirectinput.keyUp(key)

    def press(self, key: str) -> None:
        self._sleep(random.uniform(self.s.delay_min, self.s.delay_max))
        if self._background() and self._poster and getattr(self.s, "background_post_keys", False) and self._poster(key):
            return
        else:
            if self._focuser and (not self._background()):
                self._focuser()
            with self._input_context("key"):
                self._presser(key)

    def ready(self) -> bool:
        return self._clock() - self._last_click >= self.s.click_cooldown

    def click(self, x: int, y: int) -> bool:
        if not self.ready():
            return False
        else:
            j = self.s.jitter_px
            if self._humanize() and j > 0:
                tx, ty = (x + humanizer.gauss_offset(self._rng), y + humanizer.gauss_offset(self._rng))
            else:
                tx, ty = (x + random.randint(-j, j), y + random.randint(-j, j))
            self._sleep(random.uniform(self.s.delay_min, self.s.delay_max))
            with self._input_context("click", (tx, ty)) as ctx:
                if getattr(ctx, "click_blocked", False):
                    return False
                else:
                    self._clicker(tx, ty)
            self._last_click = self._clock()
            return True

    def user_away(self) -> bool:
        try:
            return bool(self._background() and self._away and self._away())
        except Exception:
            return False

    def look(self, dx: int, dy: int, duration_ms: int, force: bool = False) -> None:
        if self.user_away() and (not force):
            return
        if force or not self._background():
            if self._focuser:
                self._focuser()
            move_camera_smooth(dx, dy, duration_ms, self._mover, self._sleep, self._rng)
        else:
            with self._input_context("key"):
                move_camera_smooth(dx, dy, duration_ms, self._mover, self._sleep, self._rng)

    def swing(self) -> bool:
        if self.user_away():
            return False
        else:
            pos = self._cursor()
            if not pos:
                return False
            else:
                tx, ty = (pos[0] + humanizer.gauss_offset(self._rng), pos[1] + humanizer.gauss_offset(self._rng))
                if self._focuser and (not self._background()):
                    self._focuser()
                with self._input_context("click", (tx, ty)) as ctx:
                    if getattr(ctx, "click_blocked", False):
                        return False
                    else:
                        self._swinger(tx, ty, self._rng.uniform(0.06, 0.12))
                return True


class SettingsAdapter:
    def __init__(self, backing):
        object.__setattr__(self, "_b", backing)
        from config import Settings as ConfigSettings

        object.__setattr__(self, "_defaults", ConfigSettings())

    def __getattr__(self, name):
        b = object.__getattribute__(self, "_b")
        values = getattr(b, "values", {})
        if name in values:
            return values[name]
        try:
            v = b.get(name, None)
        except Exception:
            v = None
        if v is None:
            defaults = object.__getattribute__(self, "_defaults")
            if hasattr(defaults, name):
                return getattr(defaults, name)
            raise AttributeError(name)
        return v

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_b").set(name, value)


class MacroController:
    def __init__(
        self,
        settings,
        on_log: Optional[Callable[[str], None]] = None,
        on_state: Optional[Callable[[str, float, int], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        reporter=None,
        worker_factory=None,
        on_update: Optional[Callable[[dict], None]] = None,
        saver: Optional[Callable[[object], None]] = None,
        on_started: Optional[Callable[[], None]] = None,
        on_stopped: Optional[Callable[[], None]] = None,
        on_idle: Optional[Callable[[], None]] = None,
        on_discord: Optional[Callable[[str, str], None]] = None,
    ):
        self.s = settings if hasattr(settings, "mode") else SettingsAdapter(settings)
        from config import user_settings_path

        self.settings_path = getattr(settings, "path", None) or user_settings_path()
        self._on_log = on_log or (lambda _m: None)
        self._on_state = on_state or (lambda _s, _c, _l: None)
        self._on_error = on_error or (lambda _m: None)
        self.reporter = reporter
        self._worker_factory = worker_factory
        self._saver = saver
        self._on_started = on_started or (lambda: None)
        self._on_stopped = on_stopped or (lambda: None)
        self._on_idle = on_idle or (lambda: None)
        self._on_discord = on_discord or (lambda _m, _k: None)
        self._on_update = on_update or (lambda _d: None)
        self._start_lock = threading.Lock()
        self.status = _SignalDict({"state": "IDLE", "score": 0.0, "loops": 0}, self._on_update)
        self.worker = None
        self._log_q = _CallbackQueue(self._on_log)

    def running(self) -> bool:
        return bool(self.worker and self.worker.is_alive() and (not self.worker.stop_event.is_set()))

    def stopping(self) -> bool:
        return bool(self.worker and self.worker.is_alive() and self.worker.stop_event.is_set())

    def snapshot(self) -> dict:
        return dict(self.status)

    def start(self) -> bool:
        old = self.worker
        if old is not None and old.is_alive():
            if not old.stop_event.is_set():
                return False
            old.join(3.0)
            if old.is_alive():
                self._on_error("previous worker is still stopping")
                return False
        with self._start_lock:
            if self.running():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False
            try:
                if self.reporter:
                    self.reporter.begin_session(self.s.mode, self.s.lang)
                factory = self._worker_factory
                if factory is None:
                    from worker import Worker as factory
                self.worker = factory(self.s, self._log_q, self.status, self.reporter)
                self.worker.start()
                threading.Thread(
                    target=self._watch_worker, args=(self.worker,), daemon=True, name="FNauto-worker-watch"
                ).start()
                self._on_log(i18n.t(self.s.lang, "log_started"))
                if self._saver:
                    self._saver(self.s)
                self._on_started()
                return True
            except Exception as e:
                self._on_error(str(e))
                return False

    def stop(self) -> None:
        w = self.worker
        if w:
            w.stop_event.set()
        self._on_state("IDLE", 0.0, self.status.get("loops", 0))
        self._on_log(i18n.t(self.s.lang, "log_stopped"))
        self._finish_session()
        if w is not None and w.is_alive():
            threading.Thread(target=self._watch_worker, args=(w,), daemon=True, name="FNauto-stop-watch").start()
        else:
            self._after_stop(w)

    def _watch_worker(self, w) -> None:
        while w.is_alive():
            try:
                w.join(0.25)
            except Exception:
                break
        if not w.is_alive() and not self.running():
            self._after_stop(w)

    def _after_stop(self, w=None) -> None:
        if w is not None:
            if getattr(w, "_ui_idle_done", False):
                return
            w._ui_idle_done = True
        self._on_stopped()
        self._on_idle()

    def _finish_session(self) -> None:
        if self.reporter and getattr(self.s, "telemetry_enabled", False):

            def done(status: str) -> None:
                if status == "ok":
                    self._on_discord("Discord: session summary sent", "info")
                else:
                    self._on_discord(f"Discord: session summary failed ({status})", "warning")

            self.reporter.send_session_summary(callback=done)

    def join(self, timeout: Optional[float] = None) -> None:
        if self.worker:
            self.worker.join(timeout)


class _SignalDict(dict):
    def __init__(self, initial, callback):
        super().__init__(initial)
        self._callback = callback

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._callback(dict(self))

    def update(self, *a, **k):
        super().update(*a, **k)
        self._callback(dict(self))


class _CallbackQueue:
    def __init__(self, callback):
        self._callback = callback

    def put(self, item, *_args, **_kwargs) -> None:
        self._callback(str(item))
