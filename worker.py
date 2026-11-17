import os
import queue
import threading
import time
from pathlib import Path
import cv2
import config
import i18n
from anti_afk import AntiAfk
from audio_mute import GameAudioController
from bus_drop import BusDrop
from background_input import BackgroundInput
from config import Settings
from controller import Controller
from focus import ensure_game_foreground
from humanizer import CoffeeBreak
from loot_vault import LootVault
from mode_b import ModeB
from mode_c import ModeC
from discord_webhook import DiscordReporter, _duration_text
from reward_shot import RewardShotSender
from rescue import Rescue
from relauncher import GameRelauncher
from space_press import SpacePresser
from state_machine import POPUP_KEYS, State, StateMachine
from vision import Plate, capture_for_matching, find_plate, find_template, load_template_auto
from watchdog import Watchdog
from window_capture import GameWindow, WindowCapture

BG_HINTS = {"minimized": "log_bg_minimized", "black": "log_bg_black", "denied": "log_bg_denied"}
STUCK_DIAG_AFTER_S = 60.0
STUCK_DIAG_EVERY_S = 120.0
STUCK_DIAG_MAX = 5


def diagnostic_dir(settings) -> str:
    base = os.path.dirname(getattr(settings, "path", "")) or config.base_dir()
    return os.path.join(base, "diagnostics")


def save_diagnostic_frame(frame, settings) -> str:
    try:
        folder = diagnostic_dir(settings)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, time.strftime("IN_MATCH_%Y%m%d_%H%M%S.png"))
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            return ""
        Path(path).write_bytes(buf.tobytes())
        return path
    except Exception:
        return ""


def load_templates(lang: str) -> dict:
    templates = {
        k: load_template_auto(config.template_path(k, lang), config.PLATES.get(k))
        if config.uses_template(k, lang)
        else None
        for k in config.TEMPLATE_NAMES
    }
    plate_path = os.path.join(config.assets_dir(), "return_lobby_btn_plate.png")
    if not os.path.isfile(plate_path):
        plate_path = os.path.join(config.bundled_assets_dir(), "return_lobby_btn_plate.png")
    templates["return_lobby_plate"] = load_template_auto(
        plate_path, {"roi": config.PLATES["return_lobby"]["roi"], "threshold": config.PLATES["return_lobby"]["threshold"]}
    )
    for key, filename in (
        ("return_lobby_text_en", "return_lobby_btn_en.png"),
        ("return_lobby_text_ja", "return_lobby_btn.png"),
    ):
        text_path = os.path.join(config.assets_dir(), filename)
        if not os.path.isfile(text_path):
            text_path = os.path.join(config.bundled_assets_dir(), filename)
        templates[key] = load_template_auto(text_path)
    return templates


class Worker(threading.Thread):
    def __init__(
        self, settings: Settings, log_q: "queue.Queue[str]", status: dict, reporter: "DiscordReporter | None" = None
    ):
        super().__init__(daemon=True)
        self.s = settings
        self.log_q = log_q
        self.status = status
        self.reporter = reporter
        self.stop_event = threading.Event()
        self.commands = queue.Queue()

    def _load_templates(self, lang: str) -> dict:
        templates = load_templates(lang)
        for k, v in templates.items():
            if v is None and k not in config.OPTIONAL_TEMPLATES and config.uses_template(k, lang):
                self.log_q.put(f"template missing: {config.template_filename(k, lang)}")
        return templates

    def _drain_commands(self, ctrl, audio, sm, frame, ox, oy) -> None:
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                return
            try:
                if isinstance(cmd, tuple):
                    if cmd[0] == "tap" and frame is not None:
                        ctrl.click(int(float(cmd[1]) * frame.shape[1]) + ox, int(float(cmd[2]) * frame.shape[0]) + oy)
                    elif cmd[0] == "key":
                        key = "1" if cmd[1] == "pickaxe" else str(cmd[1])
                        ctrl.press(key)
                elif cmd == "space":
                    ctrl.press("space")
                elif cmd == "click" and frame is not None:
                    ctrl.click(frame.shape[1] // 2 + ox, frame.shape[0] // 2 + oy)
                elif cmd == "mute":
                    if self.s.auto_mute_enabled:
                        audio.refresh()
                    else:
                        audio.restore()
            except Exception as e:
                self.log_q.put(f"command {cmd}: {type(e).__name__}: {e}")

    def run(self) -> None:
        lang = self.s.lang
        templates = self._load_templates(lang)
        locator = GameWindow()
        wcap = WindowCapture(locator)
        bg = BackgroundInput(locator, self.s, marker_path=os.path.join(config.base_dir(), "FNauto_shield.json"))
        bg.start()
        bg_stop = threading.Event()
        threading.Thread(target=bg.watch, args=(bg_stop,), daemon=True, name="FNauto-ghost").start()
        ctrl = Controller(
            self.s,
            focuser=ensure_game_foreground,
            swapper=bg.context,
            poster=lambda key: bg.post_tap(key),
            away=getattr(bg, "other_window_in_front", None),
        )
        mode_a = StateMachine(self.s, templates, ctrl)
        machines = {"A": mode_a, "B": ModeB(self.s, templates, ctrl), "C": ModeC(self.s, templates, ctrl, mode_a)}
        mode = self.s.mode if self.s.mode in machines else "A"
        sm = machines[mode]
        sm.start()
        vault = LootVault(log=self.log_q.put)
        rshot = RewardShotSender(self.s, reporter=self.reporter, log=self.log_q.put)

        def on_claim(key, frame, loops):
            if self.s.loot_vault_enabled:
                vault.save(frame, loops)
            rshot.notify(frame)

        for m in machines.values():
            m.log = self.log_q.put
            m.on_claim = on_claim
        audio = GameAudioController(log=self.log_q.put)
        audio_t = 0.0
        coffee = CoffeeBreak(self.s)

        def find_popup(frame):
            for key in POPUP_KEYS:
                tpl = templates.get(key)
                if tpl is None:
                    continue
                else:
                    m, _ = (
                        find_plate(frame, tpl, self.s.scales)
                        if isinstance(tpl, Plate)
                        else find_template(frame, tpl, self.s.threshold, self.s.scales)
                    )
                    if m:
                        return (m[0], m[1])
            return

        def send_stuck(state: str, minutes: int) -> None:
            if self.reporter and self.s.alert_enabled:
                self.reporter.send_stuck(state, minutes)

        resc = Rescue(self.s, ctrl, lambda: sm, find_popup=find_popup, send_stuck=send_stuck, log=self.log_q.put)

        def in_match() -> bool:
            if isinstance(sm, ModeB):
                return sm.match_active()
            else:
                return sm.state is State.IN_MATCH

        afk = AntiAfk(
            self.s,
            active=in_match,
            focuser=ensure_game_foreground,
            swapper=bg.context,
            look=lambda dx, dy, ms, force=True: ctrl.look(dx, dy, ms, force=force),
            swing=ctrl.swing,
            dive_look=lambda dx, dy, ms: ctrl.look(dx, dy, ms, force=True),
            away=getattr(bg, "other_window_in_front", None),
            defer=bg.user_busy,
            post_down=lambda k: bg.post_key(k, True),
            post_up=lambda k: bg.post_key(k, False),
        )
        bus = BusDrop(self.s, log=self.log_q.put)
        afk_thread = threading.Thread(target=afk.run, args=(self.stop_event, self.log_q.put), daemon=True)
        afk_thread.start()
        def space_active() -> bool:
            if getattr(self.s, "movement_profile", "continuous") == "continuous":
                return False
            return in_match()

        space = SpacePresser(self.s, active=space_active, press=lambda: ctrl.press("space"), defer=bg.user_busy)
        space_thread = threading.Thread(target=space.run, args=(self.stop_event, self.log_q.put), daemon=True)
        space_thread.start()
        self.relauncher = GameRelauncher(self.s, log=self.log_q.put)
        rel_thread = threading.Thread(
            target=self.relauncher.run, args=(self.stop_event,), daemon=True, name="FNauto-relauncher"
        )
        rel_thread.start()
        last_note, last_score, last_src = ("", (-1.0), "")
        diag_state = None
        diag_since = time.monotonic()
        diag_last = 0.0
        diag_count = 0
        last_treasure_shot = -1000.0
        last_completed_loops = sum((m.loops for m in machines.values()))
        match_start_mono = None
        match_start_wall = None

        def alert(code: str, detail: str) -> None:
            if self.reporter and self.s.alert_enabled:
                self.reporter.send_alert(code, detail)

        dog = Watchdog(alert)
        try:
            while not self.stop_event.is_set():
                try:
                    if self.s.lang != lang:
                        lang = self.s.lang
                        templates = self._load_templates(lang)
                        for m in machines.values():
                            m.templates = templates
                    if self.s.mode != mode and self.s.mode in machines:
                        sm.stop()
                        mode = self.s.mode
                        sm = machines[mode]
                        sm.start()
                        if self.reporter:
                            self.reporter.set_mode(mode)
                    now_m = time.monotonic()
                    if now_m - audio_t >= 30.0:
                        audio_t = now_m
                        if self.s.auto_mute_enabled:
                            audio.refresh()
                        else:
                            audio.restore()
                    pause = coffee.check(sm.state.value)
                    if pause:
                        self.log_q.put(f"[humanizer] coffee break ({int(pause)}s)")
                        self.stop_event.wait(pause)
                        resc.progress()
                        continue
                    with bg.capture_guard():
                        frame, ox, oy, src = capture_for_matching(
                            self.s.monitor_index, wcap if self.s.background_mode else None
                        )
                    self._drain_commands(ctrl, audio, sm, frame, ox, oy)
                    if src != last_src:
                        last_src = src
                        if src in BG_HINTS:
                            self.log_q.put(i18n.t(self.s.lang, BG_HINTS[src]))
                    note = bg.ghost_notice(src)
                    if note:
                        self.log_q.put(i18n.t(self.s.lang, note))
                    r = sm.step(frame, ox, oy)
                    now_diag = time.monotonic()
                    if mode == "A" and r.state is State.IN_MATCH:
                        if diag_state is not State.IN_MATCH:
                            diag_state = State.IN_MATCH
                            diag_since = now_diag
                            diag_last = 0.0
                            diag_count = 0
                        elif (
                            diag_count < STUCK_DIAG_MAX
                            and now_diag - diag_since >= STUCK_DIAG_AFTER_S
                            and (diag_last == 0.0 or now_diag - diag_last >= STUCK_DIAG_EVERY_S)
                        ):
                            scores = sm.diagnose(frame)
                            path = save_diagnostic_frame(frame, self.s)
                            message = f"[diag] IN_MATCH {int(now_diag - diag_since)}s without a transition: {scores}"
                            if path:
                                message += f" frame={path}"
                            self.log_q.put(message)
                            diag_last = now_diag
                            diag_count += 1
                    else:
                        diag_state = r.state
                        diag_since = now_diag
                        diag_last = 0.0
                        diag_count = 0
                    try:
                        if sm.state.value in ("B:LOBBY", "SEARCHING_PLAY"):
                            self.relauncher.note_play()
                        self.relauncher.note_step(frame, r.clicked)
                    except Exception:
                        pass
                    dog.ok()
                    if in_match() and bus.observe(frame):
                        afk.dive_async(self.stop_event, self.log_q.put)
                    if in_match() and getattr(self.s, "treasure_shot_enabled", True):
                        ttpl = templates.get("pirate_token")
                        if ttpl is None:
                            ttpl = templates.get("treasure_reward_banner")
                        if ttpl is None:
                            ttpl = templates.get("treasure_reward")
                        if ttpl is not None and (now_m - last_treasure_shot >= 15.0):
                            try:
                                fh, fw = frame.shape[:2]
                                rx0, ry0 = int(0.28 * fw), int(0.04 * fh)
                                rx1, ry1 = int(0.72 * fw), int(0.42 * fh)
                                roi = frame[ry0:ry1, rx0:rx1]
                                if isinstance(ttpl, Plate):
                                    tm, tscore = find_plate(frame, ttpl, self.s.scales)
                                else:
                                    tm, tscore = find_template(roi, ttpl, 0.72, self.s.scales)
                                if tm:
                                    last_treasure_shot = now_m
                                    self.log_q.put(f"[treasure] Pirate Token reward detected! (score: {tscore:.2f}) saving full screenshot...")
                                    vault.save_treasure(frame, sm.loops)
                                    rshot.notify_treasure(frame)
                            except Exception:
                                pass
                    if r.clicked:
                        dog.action(f"{r.state.value}:{r.key}")
                    dog.tick()
                    self.status.update(state=r.state.value, score=r.score, loops=sm.loops)
                    resc.tick(r.state.value, r.clicked, frame, ox, oy)
                    current_loops = sum((m.loops for m in machines.values()))
                    if current_loops > last_completed_loops:
                        now_wall = time.time()
                        now_mono = time.monotonic()
                        if match_start_mono is not None and match_start_wall is not None:
                            duration_s = int(max(0, now_mono - match_start_mono))
                            start_wall = match_start_wall
                        else:
                            duration_s = 0
                            start_wall = now_wall
                        time_taken = _duration_text(duration_s)
                        time_from = time.strftime("%H:%M:%S", time.localtime(start_wall))
                        time_to = time.strftime("%H:%M:%S", time.localtime(now_wall))
                        for match_idx in range(last_completed_loops + 1, current_loops + 1):
                            self.log_q.put(
                                f"[match] Match {match_idx} completed ({time_taken}, from {time_from} to {time_to})"
                            )
                            if self.reporter:
                                self.reporter.send_match_completed(
                                    match_num=match_idx,
                                    time_taken=time_taken,
                                    time_from=time_from,
                                    time_to=time_to,
                                )
                        last_completed_loops = current_loops
                        match_start_mono = None
                        match_start_wall = None
                    elif current_loops < last_completed_loops:
                        last_completed_loops = current_loops

                    if match_start_mono is None:
                        if (r.clicked and r.key in ("play", "storefront_play")) or in_match() or sm.state is State.A_LOADING:
                            match_start_mono = time.monotonic()
                            match_start_wall = time.time()
                    elif r.clicked and r.key in ("play", "storefront_play"):
                        match_start_mono = time.monotonic()
                        match_start_wall = time.time()

                    if self.reporter:
                        if r.clicked:
                            self.reporter.record_action()
                        self.reporter.set_loops(current_loops)
                        self.reporter.set_popups(sum((m.rewards.count for m in machines.values())))
                        self.reporter.set_claims(sum((m.claims for m in machines.values())))
                        self.reporter.maybe_send_periodic(self.s.report_hours if self.s.telemetry_enabled else 0)
                    if r.note != last_note or r.clicked or abs(r.score - last_score) > 0.1:
                        self.log_q.put(f"[{r.state.value}] {r.note} ({r.score:.2f}/{self.s.threshold:.2f})")
                        last_note, last_score = (r.note, r.score)
                except Exception as e:
                    self.log_q.put(f"error: {e}")
                    dog.error(f"{type(e).__name__}: {e}")
                wait_s = 1.0 if in_match() else config.get_jittered_wait(self.s.poll_interval, self.s)
                self.stop_event.wait(wait_s)
        except BaseException as e:
            dog.fatal(f"{type(e).__name__}: {e}")
            raise
        finally:
            bg_stop.set()
            self.s.rescue_listening = False
            try:
                audio.restore()
            except Exception:
                pass
            try:
                afk_thread.join(timeout=2)
                space_thread.join(timeout=2)
                rel_thread.join(timeout=2)
            finally:
                bg.release_all()
        self.status.update(state=State.IDLE.value, score=0.0)
