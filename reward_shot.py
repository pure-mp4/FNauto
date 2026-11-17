import threading
import time
from typing import Callable, Optional

import numpy as np
import shot


class RewardShotSender:
    COOLDOWN_S = 300.0
    TREASURE_COOLDOWN_S = 10.0

    def __init__(
        self,
        settings,
        reporter=None,
        log: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        sync: bool = False,
    ):
        self.s = settings
        self.reporter = reporter
        self.log = log or (lambda _message: None)
        self._clock = clock
        self._sync = sync
        self._last = None
        self._last_treasure = None
        self._busy = threading.Lock()
        self.sent = 0
        self.skipped = 0

    def allowed(self) -> bool:
        return bool(
            getattr(self.s, "reward_shot_enabled", False)
            and self.reporter is not None
            and getattr(self.reporter, "configured", False)
        )

    def allowed_treasure(self) -> bool:
        return bool(
            getattr(self.s, "treasure_shot_enabled", True)
            and self.reporter is not None
            and getattr(self.reporter, "configured", False)
        )

    def notify_treasure(self, frame: np.ndarray) -> bool:
        if not self.allowed_treasure():
            return False
        try:
            now = self._clock()
            if self._last_treasure is not None and now - self._last_treasure < self.TREASURE_COOLDOWN_S:
                return False
            if not self._busy.acquire(blocking=False):
                return False
            self._last_treasure = now
            picture = np.array(frame, copy=True)
            if self._sync:
                self._run(picture, "treasure")
                return True
            threading.Thread(target=self._run, args=(picture, "treasure"), daemon=True, name="FNauto-treasure-shot").start()
            return True
        except Exception:
            return False

    def notify(self, frame: np.ndarray) -> bool:
        if not self.allowed():
            return False
        try:
            now = self._clock()
            if self._last is not None and now - self._last < self.COOLDOWN_S:
                self.skipped += 1
                return False
            if not self._busy.acquire(blocking=False):
                return False
            self._last = now
            picture = np.array(frame, copy=True)
            if self._sync:
                self._run(picture, "reward")
                return True
            threading.Thread(target=self._run, args=(picture, "reward"), daemon=True, name="FNauto-reward-shot").start()
            return True
        except Exception:
            return False

    def _run(self, frame: np.ndarray, kind: str = "reward") -> str:
        try:
            jpeg = shot.encode_jpeg(frame)
            if jpeg is None:
                self.log(f"{kind} screen: could not encode the picture")
                return "no_picture"
            status = "server"
            callback_status = []

            def done(value):
                callback_status.append(value)

            if kind == "treasure" and hasattr(self.reporter, "send_treasure"):
                self.reporter.send_treasure(jpeg, callback=done)
            else:
                self.reporter.send_screenshot(jpeg, callback=done)
            if not self._sync:
                self.log(f"{kind} screen: queued for Discord")
                return "queued"
            status = callback_status[0] if callback_status else "queued"
            self.log(f"{kind} screen: {status}")
            if status == "ok":
                self.sent += 1
            return status
        except Exception as error:
            self.log(f"{kind} screen: {type(error).__name__}")
            return "error"
        finally:
            self._busy.release()
