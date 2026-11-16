import time
from typing import Callable, Optional, Tuple

STAGE2_AFTER_S = 120.0
MATCH_STUCK_S = 2100.0


class Rescue:
    def __init__(
        self,
        settings,
        ctrl,
        get_machine: Callable[[], object],
        find_popup: Optional[Callable[[object], Optional[Tuple[int, int]]]] = None,
        send_stuck: Optional[Callable[[str, int], None]] = None,
        log: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.s = settings
        self.ctrl = ctrl
        self._machine = get_machine
        self._find_popup = find_popup
        self._send_stuck = send_stuck
        self.log = log or (lambda _message: None)
        self._clock = clock
        self.stage = 0
        self.last_frame = None
        self._state = None
        self._t_progress = clock()
        self._t_stage1 = 0.0

    @property
    def stuck(self) -> bool:
        return self.stage >= 1

    def progress(self) -> None:
        self._t_progress = self._clock()
        if self.stage:
            self.stage = 0
            self.s.rescue_listening = False

    def tick(self, state_value: str, clicked: bool, frame, ox: int = 0, oy: int = 0) -> None:
        try:
            self._tick(state_value, clicked, frame, ox, oy)
        except Exception as error:
            self.log(f"[rescue] error: {type(error).__name__}: {error}")

    def _tick(self, state_value, clicked, frame, ox, oy) -> None:
        now = self._clock()
        self.last_frame = frame
        if clicked or state_value != self._state:
            self._state = state_value
            self.progress()
        timeout = float(getattr(self.s, "stuck_timeout_min", 0.0)) * 60.0
        if timeout > 0 and state_value == "IN_MATCH":
            timeout = max(timeout, MATCH_STUCK_S)
        if timeout > 0:
            idle = now - self._t_progress
            if self.stage == 0 and idle >= timeout:
                self.stage, self._t_stage1 = 1, now
                self.log("[rescue] stuck detected, attempting Esc recovery")
                self.ctrl.press("esc")
                if self._find_popup is not None:
                    position = self._find_popup(frame)
                    if position:
                        self.ctrl.click(position[0] + ox, position[1] + oy)
            elif self.stage == 1 and now - self._t_stage1 >= STAGE2_AFTER_S:
                self.stage = 2
                minutes = int(idle // 60)
                self.log(f"[rescue] still stuck after {minutes} min: alerting")
                if self._send_stuck is not None:
                    self._send_stuck(str(state_value), minutes)
        elif self.stage:
            self.progress()
        self.s.rescue_listening = self.stage >= 1
