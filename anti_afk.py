import contextlib
import random
import threading
import time
from typing import Callable, Optional
import config
from humanizer import Humanizer

DIVE_PITCH = 1400
SWAY_S = 0.5
DIVE_RESTORE = 0.55
PICKAXE_EVERY_S = (10.0, 30.0)


class _Guard:
    pass

    def __init__(self, stop, active: Callable[[], bool], slice_s: float = 0.05):
        self._stop, self._active, self._slice = (stop, active, slice_s)

    def _alive(self) -> bool:
        try:
            return bool(self._active())
        except Exception:
            return False

    def is_set(self) -> bool:
        return self._stop.is_set() or not self._alive()

    def wait(self, timeout=None) -> bool:
        end = time.monotonic() + (timeout or 0.0)
        while True:
            if self.is_set():
                return True
            else:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                else:
                    if self._stop.wait(min(self._slice, left)):
                        return True


def _halted(stop) -> bool:
    f = getattr(stop, "is_set", None)
    return bool(f and f())


def _default_key_down(key: str) -> None:
    import pydirectinput

    pydirectinput.FAILSAFE = False
    pydirectinput.PAUSE = 0.0
    pydirectinput.keyDown(key)


def _default_key_up(key: str) -> None:
    import pydirectinput

    pydirectinput.FAILSAFE = False
    pydirectinput.PAUSE = 0.0
    pydirectinput.keyUp(key)


class AntiAfk:
    def __init__(
        self,
        settings,
        active: Callable[[], bool],
        key_down: Optional[Callable[[str], None]] = None,
        key_up: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        focuser: Optional[Callable[[], object]] = None,
        swapper: Optional[Callable[..., object]] = None,
        defer: Optional[Callable[[], bool]] = None,
        post_down: Optional[Callable[[str], bool]] = None,
        post_up: Optional[Callable[[str], bool]] = None,
        look: Optional[Callable[[int, int, int], None]] = None,
        swing: Optional[Callable[[], object]] = None,
        dive_look: Optional[Callable[[int, int, int], None]] = None,
        rng: Optional[random.Random] = None,
        away: Optional[Callable[[], bool]] = None,
    ):
        self.s = settings
        self.active = active
        self._focuser = focuser
        self._swapper = swapper
        self._defer = defer
        self._post_down, self._post_up = (post_down, post_up)
        self._down = key_down or _default_key_down
        self._up = key_up or _default_key_up
        self._clock = clock
        self._look = look
        self._swing = swing
        self._dive_look = dive_look
        self._diving = threading.Event()
        self._away = away
        self._rng = rng or random.Random()
        self._hum = Humanizer()
        self._pickaxe_due = None
        self.last_pattern = ""
        self._ratio = 1.0
        self.last_hold = 0.0
        self._last_key = ""
        self._held_keys = set()

    def _humanize(self) -> bool:
        return bool(getattr(self.s, "humanizer_enabled", False))

    def _background(self) -> bool:
        return bool(self._swapper and getattr(self.s, "background_mode", False))

    def _input_context(self):
        if self._background():
            return self._swapper("key", None)
        else:
            return contextlib.nullcontext()

    def _use_post(self) -> bool:
        return bool(
            self._background() and self._post_down and self._post_up and getattr(self.s, "background_post_keys", False)
        )

    def _can_look(self) -> bool:
        return bool(self._look and getattr(self.s, "afk_mouse_look", True)) and (not self._user_away())

    def _user_away(self) -> bool:
        try:
            return bool(self._background() and self._away and self._away())
        except Exception:
            return False

    def _look_around(self) -> None:
        if not self._can_look():
            return
        else:
            try:
                dx, dy, ms = self._hum.pitch.next_look()
                self._look(dx, dy, ms)
            except Exception:
                return None

    def _tap(self, key: str, dur: float) -> None:
        with self._input_context():
            self._down(key)
            try:
                if dur > 0:
                    time.sleep(dur)
            finally:
                self._up(key)

    def _tap_hold(self, stop: threading.Event, key: str, dur: float) -> bool:
        with self._input_context():
            self._down(key)
        try:
            return bool(stop.wait(dur))
        finally:
            with self._input_context():
                self._up(key)

    def _pick_key(self, keys) -> str:
        options = [k for k in keys if k != self._last_key] or list(keys)
        key = self._rng.choice(options)
        self._last_key = key
        return key

    def _look_sway(self) -> None:
        if not self._can_look():
            return None
        else:
            try:
                dx = self._rng.choice(((-1), 1)) * self._rng.randint(30, 90)
                self._look(dx, self._rng.randint(-3, 3), self._rng.randint(160, 380))
            except Exception:
                return None

    def _weave(self, key: str, hold: float) -> list:
        if not self._humanize() or hold < 1.2:
            return []
        r = self._rng
        options = [k for k in ("a", "d") if k != key] or ["a", "d"]
        side, at, plan = (r.choice(options), 0.0, [])
        for _ in range(3):
            at += r.uniform(0.25, 0.7) if not plan else r.uniform(0.3, 0.8)
            dur = min(r.uniform(0.15, 0.45), hold - at - 0.15)
            if dur < 0.12:
                break
            plan.append((at, side, dur))
            at += dur
            side = options[0] if side != options[0] else options[-1]
        return plan

    def _wait_until(self, stop, started: float, target: float) -> bool:
        left = target - (self._clock() - started)
        return _halted(stop) if left <= 0 else bool(stop.wait(left))

    def press_once(self, stop: threading.Event) -> str:
        if not self._humanize():
            self.last_pattern = "-"
            return self._strafe(stop)
        else:
            pat = self._hum.pattern()
            if pat == "D" and (not self._can_look()):
                pat = "A"
            self.last_pattern = pat
            try:
                if pat == "B":
                    return self._jump_walk(stop)
                else:
                    if pat == "C":
                        return self._fidget(stop)
                    else:
                        if pat == "D":
                            return self._micro_pause(stop)
                        else:
                            if self._can_look() and self._rng.random() < 0.35 and (not _halted(stop)):
                                self._look_around()
                            return self._strafe(stop)
            except Exception:
                self.release_all()
                raise

    def _strafe(self, stop: threading.Event) -> str:
        key = self._pick_key(self.s.afk_keys)
        hold = self._hum.hold(self.s.afk_hold) if self._humanize() else self.s.afk_hold
        self.last_hold = hold
        posted = self._use_post() and self._post_down(key)
        if not posted:
            if self._focuser and (not self._background()):
                self._focuser()
            with self._input_context():
                self._down(key)
        try:
            if posted:
                stop.wait(hold)
            else:
                started = self._clock()

                def left():
                    return hold - (self._clock() - started)

                for at, side, dur in self._weave(key, hold):
                    if self._wait_until(stop, started, at):
                        break
                    if left() > dur + SWAY_S and self._can_look() and self._rng.random() < 0.5:
                        self._look_sway()
                    if left() < dur:
                        break
                    if self._tap_hold(stop, side, dur):
                        break
                self._wait_until(stop, started, hold)
        finally:
            if posted:
                self._post_up(key)
            else:
                with self._input_context():
                    self._up(key)
        return key

    def _jump_walk(self, stop: threading.Event) -> str:
        r = self._rng
        hold = self._hum.hold(self.s.afk_hold)
        self.last_hold = hold
        if self._focuser and (not self._background()):
            self._focuser()
        with self._input_context():
            self._down("w")
        started = self._clock()
        try:
            tap = min(r.uniform(0.08, 0.18), max(0.05, hold - 0.1))
            lead = min(r.uniform(0.3, 0.8), max(0.1, hold - tap - 0.02))
            if not self._wait_until(stop, started, lead) and (not _halted(stop)):
                self._tap_hold(stop, "space", tap)
            self._wait_until(stop, started, hold)
        finally:
            with self._input_context():
                self._up("w")
        return "w"

    def _fidget(self, stop: threading.Event) -> str:
        r = self._rng
        key = self._pick_key(self.s.afk_keys)
        self.last_hold = 0.0
        if self._focuser and (not self._background()):
            self._focuser()
        for n in range(2):
            if _halted(stop):
                break
            dur = r.uniform(0.12, 0.25)
            self.last_hold += dur
            self._tap(key, dur)
            if n == 0:
                stop.wait(r.uniform(0.06, 0.18))
        return key

    def _micro_pause(self, stop: threading.Event) -> str:
        r = self._rng
        self.last_hold = 0.0
        for _ in range(r.randint(1, 3)):
            if _halted(stop):
                break
            self._look_around()
            if stop.wait(r.uniform(0.4, 1.2)):
                break
        return "-"

    def pickaxe_swing(self, stop: threading.Event) -> bool:
        if not self._swing or self._user_away():
            return False
        r = self._rng
        slot = getattr(self.s, "pickaxe_slot_key", "1") or "1"
        self.release_all()
        if self._focuser and (not self._background()):
            self._focuser()
        try:
            if _halted(stop):
                return False
            self._tap(slot, r.uniform(0.08, 0.15))
            if stop.wait(r.uniform(0.2, 0.4)) or _halted(stop):
                return False
            return bool(self._swing())
        finally:
            self.release_all()

    def dive_async(self, stop: threading.Event, log: Callable[[str], None] = lambda _m: None) -> bool:
        if self._diving.is_set():
            return False
        else:
            self._diving.set()

            def work() -> None:
                try:
                    self.dive(stop, log)
                except Exception as e:
                    log(f"bus drop error: {e}")
                finally:
                    self.release_all()
                    self._diving.clear()

            threading.Thread(target=work, daemon=True, name="FNauto-dive").start()
            return True

    def dive(self, stop: threading.Event, log: Callable[[str], None] = lambda _m: None) -> bool:
        guard = _Guard(stop, self.active)
        r = self._rng
        self._diving.set()
        self.release_all()
        if self._focuser and (not self._background()):
            self._focuser()
        if guard.is_set():
            return False
        self._tap("space", r.uniform(0.08, 0.15))
        log("anti-afk: bus drop - jumped")
        if guard.wait(r.uniform(0.35, 0.7)):
            return False
        look = self._dive_look or self._look
        down = 0
        if look and (not guard.is_set()):
            try:
                for part in (0.6, 0.4):
                    look(r.randint(-12, 12), int(DIVE_PITCH * part), r.randint(260, 420))
                    down += int(DIVE_PITCH * part)
                    if guard.wait(0.12):
                        break
            except Exception:
                pass
        secs = max(0.0, float(getattr(self.s, "bus_dive_seconds", 8.0)))
        if secs > 0 and (not guard.is_set()):
            with self._input_context():
                self._down("w")
            try:
                guard.wait(secs)
            finally:
                with self._input_context():
                    self._up("w")
        if look and down and (not guard.is_set()):
            try:
                look(0, -int(down * DIVE_RESTORE), r.randint(300, 500))
            except Exception:
                pass
        self._hum.pitch.pitch = 0
        log("anti-afk: bus drop - done")
        return True

    def _pickaxe_delay(self) -> float:
        try:
            lo, hi = (float(self.s.pickaxe_min_s), float(self.s.pickaxe_max_s))
        except Exception:
            lo, hi = PICKAXE_EVERY_S
        lo, hi = (max(1.0, min(lo, hi)), max(1.0, max(lo, hi)))
        return self._rng.uniform(lo, hi)

    def _pickaxe_tick(self, now: float, stop: threading.Event, log: Callable[[str], None]) -> None:
        if not getattr(self.s, "pickaxe_afk_enabled", False) or not self._swing:
            self._pickaxe_due = None
            return
        else:
            if self._pickaxe_due is None:
                self._pickaxe_due = now + self._pickaxe_delay()
            else:
                if now < self._pickaxe_due or (self._defer and self._defer()) or (not self.active()):
                    return None
                else:
                    self._pickaxe_due = now + self._pickaxe_delay()
                    try:
                        ok = self.pickaxe_swing(_Guard(stop, self.active))
                        log("anti-afk: pickaxe swing" if ok else "anti-afk: pickaxe swing skipped")
                    except Exception as e:
                        log(f"anti-afk pickaxe error: {e}")

    def _next_ratio(self, log: Callable[[str], None]) -> None:
        ratio = 1.0
        if self._humanize():
            ratio = self._hum.interval(1.0) * self._hum.session_factor()
        jitter = bool(getattr(self.s, "jitter_enabled", False))
        if jitter:
            lo, hi = config.jitter_range(1.0, self.s)
            ratio *= self._rng.uniform(lo, hi)
        self._ratio = ratio
        if jitter:
            base = self.s.afk_interval
            lo, hi = config.jitter_range(base, self.s)
            log(f"[jitter] waiting for {base * ratio:.1f}s (range: {lo:.0f}s-{hi:.0f}s)")

    def release_all(self) -> None:
        if hasattr(self, "_held_keys"):
            self._held_keys.clear()
        for k in set(self.s.afk_keys) | {"w", "a", "s", "d", "shift", "space"}:
            try:
                self._up(k)
            except Exception:
                pass

    def _turn_camera(self, angle_deg: float = 0.0, duration_ms: int = 0) -> None:
        """
        Smoothly rotates camera horizontally between 0 and 90 degrees
        with subtle, minimal vertical pitch adjustment (slight up/down).
        """
        if not self._can_look():
            return
        r = self._rng
        if angle_deg == 0.0:
            angle_deg = r.uniform(15.0, 90.0) * r.choice((-1, 1))
        else:
            angle_deg = max(-90.0, min(90.0, float(angle_deg)))

        # Approximately 640 mouse counts per 90 degrees in Fortnite (doubled rotation value)
        dx = int(round(2.0 * (angle_deg / 90.0) * r.uniform(280, 350)))
        # Subtle vertical adjustment: slight up/down (-6 to +6 px, approx 1-3 deg)
        dy = r.randint(-6, 6)
        if duration_ms <= 0:
            duration_ms = int(round(180 + (abs(angle_deg) / 90.0) * 300 + r.uniform(-20, 40)))
            duration_ms = max(160, min(500, duration_ms))
        try:
            if self._look:
                self._look(dx, dy, duration_ms)
        except Exception:
            pass

    def _run_continuous(self, stop: threading.Event, log: Callable[[str], None] = lambda _m: None) -> None:
        r = self._rng
        self._held_keys = set()
        held_keys = self._held_keys

        def set_held(target_keys: set) -> None:
            """
            Ensures exactly target_keys are held down (via keyDown).
            Releases keys no longer in target_keys (via keyUp).
            Movement keys are HELD continuously until explicitly updated.
            """
            to_release = held_keys - target_keys
            for k in to_release:
                try:
                    self._up(k)
                except Exception:
                    pass
                held_keys.discard(k)

            to_press = target_keys - held_keys
            for k in to_press:
                try:
                    self._down(k)
                    held_keys.add(k)
                except Exception:
                    pass

        def tap_jump() -> None:
            """
            Jumps by pressing Space briefly (~0.1s) WHILE MOVEMENT KEYS REMAIN HELD!
            """
            try:
                self._down("space")
                time.sleep(r.uniform(0.08, 0.13))
            finally:
                try:
                    self._up("space")
                except Exception:
                    pass

        def clear_all() -> None:
            for k in list(held_keys):
                try:
                    self._up(k)
                except Exception:
                    pass
            held_keys.clear()
            self.release_all()

        def pick_next_action(prev_action: str) -> tuple[str, float]:
            """
            Selects the next randomized action and duration with non-repeating stochastic weights.
            Mostly sprinting, with jogging (~5s) to recover stamina, and 0-90 degree turns.
            """
            if prev_action in ("SPRINT", "PIVOT"):
                choices = [
                    ("JOG", 40),
                    ("SPRINT", 45),
                    ("PIVOT", 15),
                ]
            else:
                choices = [
                    ("SPRINT", 65),
                    ("PIVOT", 20),
                    ("JOG", 15),
                ]

            total_weight = sum(w for _, w in choices)
            roll = r.uniform(0, total_weight)
            cum = 0.0
            selected = choices[0][0]
            for act, w in choices:
                cum += w
                if roll <= cum:
                    selected = act
                    break

            if selected == "SPRINT":
                dur = r.uniform(4.0, 8.5)
            elif selected == "JOG":
                dur = r.uniform(4.0, 6.5) # user requested: "jogging for 5 secs or something"
            elif selected == "PIVOT":
                dur = r.uniform(2.5, 4.5)
            else:
                dur = r.uniform(3.5, 6.0)

            return selected, dur

        current_action, action_dur = "SPRINT", r.uniform(4.0, 7.0)
        action_start = self._clock()

        t_next_weave = self._clock() + r.uniform(2.0, 3.5)
        t_weave_end = 0.0
        weave_key = "a"

        t_next_jump = self._clock() + r.uniform(3.0, 5.0)
        t_next_turn = self._clock() + r.uniform(1.0, 10.0)
        t_next_refresh = self._clock() + 0.35
        t_w_pause_end = 0.0
        t_w_next_pause = self._clock() + r.uniform(15.0, 20.0)
        t_focus_check = 0.0

        log("[movement] organic human engine active (held keys, 0-90 deg turns, fully randomized)")

        try:
            while not stop.wait(0.025):
                now = self._clock()

                if self._diving.is_set() or not self.s.afk_enabled or not self.active():
                    if held_keys:
                        clear_all()
                    self._pickaxe_due = None
                    action_start = now
                    continue

                if now >= t_focus_check:
                    t_focus_check = now + 4.0
                    if self._focuser:
                        self._focuser()

                # Action transition
                if now - action_start >= action_dur:
                    current_action, action_dur = pick_next_action(current_action)
                    action_start = now

                    # If starting a pivot, execute a smooth 0-90 degree camera turn with subtle vertical tilt!
                    if current_action == "PIVOT":
                        turn_deg = r.uniform(25.0, 90.0) * r.choice((-1, 1))
                        self._turn_camera(turn_deg)

                # Camera turning between 0 and 90 degrees once every 1s-10s
                if now >= t_next_turn:
                    t_next_turn = now + r.uniform(1.0, 10.0)
                    turn_deg = r.uniform(15.0, 90.0) * r.choice((-1, 1))
                    self._turn_camera(turn_deg)

                # Lateral in-motion weave timing (holding A or D while moving forward/sprinting)
                if now >= t_next_weave and now >= t_weave_end:
                    weave_key = "d" if (weave_key == "a" and r.random() < 0.7) else ("a" if r.random() < 0.7 else r.choice(("a", "d")))
                    weave_dur = r.uniform(0.35, 0.85)
                    t_weave_end = now + weave_dur
                    t_next_weave = now + weave_dur + r.uniform(2.5, 4.5)
                    # Natural slight camera steer in weave direction
                    lean_deg = (15.0 if weave_key == "d" else -15.0) + r.uniform(-5, 5)
                    self._turn_camera(lean_deg, int(r.uniform(180, 260)))

                # 15-20s Run / 2s Release Cycle:
                # Every 15-20s, release W for 2s, then hold it again.
                # This guarantees a clean KeyUp -> KeyDown cycle, so even across
                # player elimination or reboot van respawn, W re-triggers fresh!
                is_w_paused = (now < t_w_pause_end)
                if now >= t_w_next_pause and not is_w_paused:
                    t_w_pause_end = now + r.uniform(1.8, 2.2)
                    t_w_next_pause = t_w_pause_end + r.uniform(15.0, 20.0)
                    is_w_paused = True

                # Build the active held keys set:
                target = set()
                if not is_w_paused:
                    # W is held to walk/run forward
                    target.add("w")

                    # Shift is held whenever sprinting or pivoting
                    if current_action in ("SPRINT", "PIVOT") and getattr(self.s, "sprint_enabled", True):
                        target.add("shift")

                    # Lateral key (A or D) is held during weaves
                    if now < t_weave_end:
                        target.add(weave_key)

                # Ensure exact key states are held (releases W & Shift cleanly during the 2s pause)
                set_held(target)

                # Periodic key heartbeat (hardware auto-repeat):
                # Re-assert target keys (especially 'w') every ~0.3-0.5s while held
                if now >= t_next_refresh:
                    t_next_refresh = now + r.uniform(0.3, 0.5)
                    for k in target:
                        try:
                            self._down(k)
                        except Exception:
                            pass

                # In-motion jumps (while moving forward, keys remain held)
                if not is_w_paused and getattr(self.s, "jump_stride_enabled", True) and now >= t_next_jump:
                    j_int = max(3.0, float(getattr(self.s, "jump_stride_interval_s", 5.0)))
                    t_next_jump = now + r.uniform(j_int * 0.8, j_int * 1.25)
                    tap_jump()

                # Pickaxe swing without interrupting held keys
                if getattr(self.s, "pickaxe_afk_enabled", False) and self._swing:
                    if self._pickaxe_due is None:
                        self._pickaxe_due = now + self._pickaxe_delay()
                    elif now >= self._pickaxe_due:
                        self._pickaxe_due = now + self._pickaxe_delay()
                        try:
                            self._swing()
                        except Exception:
                            pass
        finally:
            clear_all()

    def run(self, stop: threading.Event, log: Callable[[str], None] = lambda _m: None) -> None:
        if getattr(self.s, "movement_profile", "continuous") == "continuous":
            self._run_continuous(stop, log)
            return

        last = self._clock()
        try:
            while not stop.wait(0.2):
                now = self._clock()
                if self._diving.is_set():
                    last = now
                    continue
                if not self.s.afk_enabled or not self.active():
                    last = now
                    self._pickaxe_due = None
                    continue
                self._pickaxe_tick(now, stop, log)
                if now - last < self.s.afk_interval * self._ratio:
                    continue
                if self._defer and self._defer():
                    continue
                last = now
                self._next_ratio(log)
                try:
                    guard = _Guard(stop, lambda: self.s.afk_enabled and self.active())
                    key = self.press_once(guard)
                    if guard.is_set():
                        self.release_all()
                    if self._humanize():
                        log(f"anti-afk: {self.last_pattern} {key.upper()} {self.last_hold:.1f}s")
                    else:
                        log(f"anti-afk: held {key.upper()} {self.s.afk_hold:g}s")
                except Exception as e:
                    log(f"anti-afk error: {e}")
        finally:
            self.release_all()
