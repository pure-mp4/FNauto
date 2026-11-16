import functools
import os
import threading
import time
import zlib
from typing import Callable, Hashable, Optional, Tuple
import cv2
import numpy as np

CV_THREADS = 1
ENABLED = True
FAST_PATH = True
SLACK = 0.03
MARGIN_MIN = 40
FINE_STEP = 0.05
SAMPLE = 8
MAX_ITEMS = 512


def apply_cv_threads(n=None) -> int:
    try:
        if n is None:
            n = int(os.environ.get("FNAUTO_CV_THREADS", CV_THREADS))
        if int(n) > 0:
            cv2.setNumThreads(int(n))
        return int(cv2.getNumThreads())
    except Exception:
        return -1


apply_cv_threads()


def _fingerprint(frame: np.ndarray) -> Hashable:
    return (
        id(frame),
        frame.shape,
        int(frame.ctypes.data),
        zlib.crc32(np.ascontiguousarray(frame[::SAMPLE, ::SAMPLE]).tobytes()),
    )


class FrameCache:
    pass

    def __init__(self, slots: int = 2):
        self.slots = slots
        self._items = []
        self._lock = threading.Lock()

    def items(self, frame: np.ndarray) -> dict:
        if not ENABLED:
            return {}
        else:
            try:
                key = _fingerprint(frame)
            except Exception:
                return {}
            with self._lock:
                for k, _ref, d in self._items:
                    if k == key:
                        return d
                d = {}
                self._items.insert(0, (key, frame, d))
                del self._items[self.slots :]
                return d

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


FRAMES = FrameCache()


def frame_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim != 3:
        return frame
    else:
        d = FRAMES.items(frame)
        g = d.get("g")
        if g is None:
            g = d["g"] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return g


def frame_half_gray(frame: np.ndarray, gray: Optional[np.ndarray] = None) -> np.ndarray:
    d = FRAMES.items(frame)
    h = d.get("h")
    if h is None:
        h = d["h"] = cv2.resize(
            gray if gray is not None else frame_gray(frame), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA
        )
    return h


def region_half(frame: np.ndarray, box: Tuple[int, int, int, int]) -> Tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = box
    region = frame[y0:y1, x0:x1]
    d = FRAMES.items(frame)
    key = ("r", x0, y0, x1, y1)
    half = d.get(key)
    if half is None:
        half = d[key] = cv2.resize(region, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return (region, half)


class TemplateCache:
    def __init__(self, cap: int = MAX_ITEMS):
        self.cap = cap
        self._d = {}
        self._lock = threading.Lock()

    def get(self, owner: object, tag: Hashable, make: Callable[[], object]):
        if not ENABLED:
            return make()
        else:
            key = (id(owner), tag)
            hit = self._d.get(key)
            if hit is not None and hit[0] is owner:
                return hit[1]
            else:
                val = make()
                with self._lock:
                    if len(self._d) >= self.cap:
                        self._d.clear()
                    self._d[key] = (owner, val)
                return val

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


TEMPLATES = TemplateCache()


def template_gray(template: np.ndarray) -> np.ndarray:
    if template.ndim != 3:
        return template
    return TEMPLATES.get(template, "g", lambda: cv2.cvtColor(template, cv2.COLOR_BGR2GRAY))


def template_half(template: np.ndarray, gray: Optional[np.ndarray] = None) -> np.ndarray:
    return TEMPLATES.get(
        template,
        "h",
        lambda: cv2.resize(
            gray if gray is not None else template_gray(template), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA
        ),
    )


def resized(img: np.ndarray, scale: float, interp_of: Callable[[float], int], tag: Hashable = "s") -> np.ndarray:
    return TEMPLATES.get(
        img, (tag, round(scale, 4)), lambda: cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp_of(scale))
    )


def resized_to(mask: np.ndarray, shape: Tuple[int, int], scale: float) -> np.ndarray:
    return TEMPLATES.get(
        mask, ("m", round(scale, 4)), lambda: cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    )


def mask_is_full(mask: np.ndarray) -> bool:
    if not ENABLED:
        return False
    return bool(TEMPLATES.get(mask, "full", lambda: bool(mask.size > 0 and (mask == 255).all())))


class HintCache:
    pass

    def __init__(self, cap: int = MAX_ITEMS):
        self.cap = cap
        self._d = {}
        self._lock = threading.Lock()

    def get(self, owner: object, tag: Hashable) -> Optional[tuple]:
        if not ENABLED or not FAST_PATH:
            return None
        else:
            hit = self._d.get((id(owner), tag))
            return hit[1] if hit is not None and hit[0] is owner else None

    def put(self, owner: object, tag: Hashable, value: tuple) -> None:
        if not ENABLED or not FAST_PATH:
            return None
        else:
            with self._lock:
                if len(self._d) >= self.cap:
                    self._d.clear()
                self._d[id(owner), tag] = (owner, value)

    def drop(self, owner: object, tag: Hashable) -> None:
        with self._lock:
            self._d.pop((id(owner), tag), None)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


HINTS = HintCache()


def window(cx: int, cy: int, tw: int, th: int, fw: int, fh: int) -> Tuple[int, int, int, int]:
    m = max(MARGIN_MIN, tw // 2, th // 2)
    left, top = (cx - tw // 2, cy - th // 2)
    return (max(0, left - m), max(0, top - m), min(fw, left + tw + m), min(fh, top + th + m))


def fine_scales(best_scale: float) -> Tuple[float, float, float]:
    return (best_scale - FINE_STEP, best_scale, best_scale + FINE_STEP)


def reset() -> None:
    FRAMES.clear()
    TEMPLATES.clear()
    HINTS.clear()


_MISS = object()


def remember(frame: np.ndarray, key: Hashable, make: Callable[[], object]):
    if not ENABLED or not isinstance(frame, np.ndarray):
        return make()
    else:
        d = FRAMES.items(frame)
        hit = d.get(key, _MISS)
        if hit is _MISS:
            hit = d[key] = make()
        return hit


def per_frame(fn):
    name = f"{fn.__module__}.{fn.__qualname__}"

    @functools.wraps(fn)
    def wrapper(frame, *args):
        try:
            key = (name,) + args
            hash(key)
        except Exception:
            return fn(frame, *args)
        v = remember(frame, key, lambda: fn(frame, *args))
        if isinstance(v, list):
            return list(v)
        else:
            return v

    return wrapper


COARSE_SKIP: Optional[float] = 0.35


def hopeless(coarse_best: float, threshold: float) -> bool:
    return ENABLED and COARSE_SKIP is not None and (threshold <= 1.0) and (coarse_best < threshold - COARSE_SKIP)


class StaticGate:
    pass
    THUMB = (64, 36)
    MEAN_MAX = 0.05
    PEAK_MAX = 4
    MAX_RUN = 3
    MAX_AGE_S = 8.0
    ENABLED = os.environ.get("FNAUTO_STATIC_GATE", "1") != "0"

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self._thumb = None
        self._frame = None
        self._key = None
        self._t = 0.0
        self.run = 0
        self.served = 0

    def _small(self, frame: np.ndarray) -> np.ndarray:
        t = cv2.resize(frame, self.THUMB, interpolation=cv2.INTER_AREA)
        if t.ndim == 3:
            return cv2.cvtColor(t, cv2.COLOR_BGR2GRAY)
        else:
            return t

    def pick(self, frame: np.ndarray, quiet: bool, key=None) -> np.ndarray:
        try:
            if (
                not ENABLED
                or not self.ENABLED
                or (not isinstance(frame, np.ndarray))
                or (frame.ndim < 2)
                or (min(frame.shape[:2]) < 100)
            ):
                self.reset()
                return frame
            small = self._small(frame)
            now = self._clock()
            prev = self._frame
            if (
                quiet
                and prev is not None
                and (key == self._key)
                and (prev.shape == frame.shape)
                and (self.run < self.MAX_RUN)
                and (now - self._t <= self.MAX_AGE_S)
            ):
                d = cv2.absdiff(small, self._thumb)
                if float(d.mean()) < self.MEAN_MAX and int(d.max()) <= self.PEAK_MAX:
                    self.run += 1
                    self.served += 1
                    return prev
            self._thumb, self._frame, self._key, self._t, self.run = (small, frame, key, now, 0)
            return frame
        except Exception:
            self.reset()
            return frame


POOL_THREADS = 4
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from concurrent.futures import ThreadPoolExecutor

                n = max(1, min(POOL_THREADS, (os.cpu_count() or 2) - 1))
                _pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="pka-match") if n > 1 else False
    return _pool


def prefetch(frame: np.ndarray, jobs) -> None:
    try:
        jobs = list(jobs)
        pool = _get_pool() if ENABLED and len(jobs) >= 2 else None
        if not pool:
            return
        frame_gray(frame)
        frame_half_gray(frame)
        for fut in [pool.submit(j) for j in jobs]:
            try:
                fut.result()
            except Exception:
                pass
    except Exception:
        return None
