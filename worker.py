import os
import queue
import threading
import time
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
from discord_webhook import DiscordReporter
from reward_shot import RewardShotSender
from rescue import Rescue
from relauncher import GameRelauncher
from space_press import SpacePresser
from state_machine import POPUP_KEYS, State, StateMachine
from vision import Plate, capture_for_matching, find_plate, find_template, load_template_auto
from watchdog import Watchdog
from window_capture import GameWindow, WindowCapture

BG_HINTS = {"minimized": "log_bg_minimized", "black": "log_bg_black", "denied": "log_bg_denied"}


def load_templates(lang: str) -> dict:
    return {
        k: load_template_auto(config.template_path(k, lang), config.PLATES.get(k))
        if config.uses_template(k, lang)
        else None
        for k in config.TEMPLATE_NAMES
    }


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
            look=ctrl.look,
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
        space = SpacePresser(self.s, active=in_match, press=lambda: ctrl.press("space"), defer=bg.user_busy)
        space_thread = threading.Thread(target=space.run, args=(self.stop_event, self.log_q.put), daemon=True)
        space_thread.start()
        self.relauncher = GameRelauncher(self.s, log=self.log_q.put)
        rel_thread = threading.Thread(
            target=self.relauncher.run, args=(self.stop_event,), daemon=True, name="FNauto-relauncher"
        )
        rel_thread.start()
        last_note, last_score, last_src = ("", (-1.0), "")

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
                    try:
                        if sm.state.value in ("B:LOBBY", "SEARCHING_PLAY"):
                            self.relauncher.note_play()
                        self.relauncher.note_step(frame, r.clicked)
                    except Exception:
                        pass
                    dog.ok()
                    if in_match() and bus.observe(frame):
                        afk.dive_async(self.stop_event, self.log_q.put)
                    if r.clicked:
                        dog.action(f"{r.state.value}:{r.key}")
                    dog.tick()
                    self.status.update(state=r.state.value, score=r.score, loops=sm.loops)
                    resc.tick(r.state.value, r.clicked, frame, ox, oy)
                    if self.reporter:
                        if r.clicked:
                            self.reporter.record_action()
                        self.reporter.set_loops(sum((m.loops for m in machines.values())))
                        self.reporter.set_popups(sum((m.rewards.count for m in machines.values())))
                        self.reporter.set_claims(sum((m.claims for m in machines.values())))
                        self.reporter.maybe_send_periodic(self.s.report_hours if self.s.telemetry_enabled else 0)
                    if r.note != last_note or r.clicked or abs(r.score - last_score) > 0.1:
                        self.log_q.put(f"[{r.state.value}] {r.note} ({r.score:.2f}/{self.s.threshold:.2f})")
                        last_note, last_score = (r.note, r.score)
                except Exception as e:
                    self.log_q.put(f"error: {e}")
                    dog.error(f"{type(e).__name__}: {e}")
                self.stop_event.wait(config.get_jittered_wait(self.s.poll_interval, self.s))
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
