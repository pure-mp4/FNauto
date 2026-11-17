from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
import numpy as np

import config
import i18n
import version
from config import Settings
from state_machine import StateMachine, State
from anti_afk import AntiAfk


def test_v11_version():
    assert version.APP_VERSION == "1.1"


def test_v11_settings_defaults_and_validation(tmp_path):
    s = Settings()
    assert s.movement_profile == "continuous"
    assert s.sprint_enabled is True
    assert s.jump_stride_enabled is True
    assert s.treasure_shot_enabled is True
    assert s.window_w == 940
    assert s.window_h == 680
    assert s.window_maximized is False

    # Check validation via config.load_user_settings
    settings_file = tmp_path / "settings.json"
    import json
    settings_file.write_text(json.dumps({"movement_profile": "pulsed"}), encoding="utf-8")
    config.load_user_settings(s, str(settings_file))
    assert s.movement_profile == "pulsed"

    settings_file.write_text(json.dumps({"movement_profile": "invalid_profile"}), encoding="utf-8")
    s2 = Settings()
    config.load_user_settings(s2, str(settings_file))
    assert s2.movement_profile == "continuous"


def test_v11_templates_exist():
    assets_dir = Path(__file__).resolve().parents[1] / "assets"
    assert (assets_dir / "pirate_token.png").exists()
    assert "pirate_token" in config.TEMPLATE_NAMES


def test_v11_i18n_keys():
    for lang in config.LANGS:
        assert i18n.t(lang, "ex_treasure_shot")
        assert i18n.t(lang, "ex_sprint")
        assert i18n.t(lang, "ex_jump_stride")


def test_lobby_claim_priority_over_play(monkeypatch):
    from types import SimpleNamespace
    import state_machine
    
    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )
    
    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    # When both 'claim' and 'play' are visible on screen
    def fake_find_checked(frame, key, tpl, find):
        if key == "claim":
            return (640, 600, 0.95), 0.95
        if key == "play":
            return (500, 500, 0.95), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    monkeypatch.setattr(state_machine, "find_template", lambda *args, **kwargs: ((640, 600, 0.95), 0.95))
    controller = FakeController()
    templates = {"claim": dummy_tpl, "play": dummy_tpl, "hud": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)
    # Crucial upgrade: The claim popup MUST be clicked before the play button!
    assert result.key == "claim"
    assert result.clicked is True
    assert controller.clicks == [(640, 600)]


def test_anti_afk_continuous_profile(monkeypatch):
    from types import SimpleNamespace
    executed = []
    def fake_continuous(stop, log):
        executed.append("continuous")

    settings = SimpleNamespace(
        movement_profile="continuous",
        afk_enabled=True,
    )
    afk = AntiAfk(settings, active=lambda: True)
    monkeypatch.setattr(afk, "_run_continuous", fake_continuous)

    import threading
    stop = threading.Event()
    stop.set()

    afk.run(stop)
    assert executed == ["continuous"]


def test_send_match_completed_discord():
    import json
    from discord_webhook import DiscordReporter

    class FakeTransport:
        def __init__(self):
            self.calls = []
        def __call__(self, url, body, headers):
            self.calls.append((url, body, headers))
            return 204, {}, b""

    class Store:
        def __init__(self):
            self.discord_webhook_url = "https://discord.com/api/webhooks/123456789/abcdefghijklmnopqrstuvwxyz"
            self.telemetry_enabled = True

    transport = FakeTransport()
    reporter = DiscordReporter(Store(), transport=transport, sync=True)
    reporter.send_match_completed(
        match_num=1,
        time_taken="17m 25s",
        time_from="14:10:05",
        time_to="14:27:30",
    )

    assert len(transport.calls) == 1
    url, body, headers = transport.calls[0]
    payload = json.loads(body.decode("utf-8"))
    assert payload["username"] == "FNauto"
    assert "content" not in payload  # Only keep texts inside embed box, outside text removed

    embed = payload["embeds"][0]
    assert embed["title"] == "Match 1 completed"
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["Time taken"] == "17m 25s"
    assert fields["Time from"] == "14:10:05"
    assert fields["Time to"] == "14:27:30"


def test_return_lobby_threshold_allows_070_score(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    # return_lobby scored 0.70 (which used to fail under 0.82)
    def fake_find_checked(frame, key, tpl, find):
        if key == "return_lobby":
            return (700, 400), 0.70
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"return_lobby": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.RETURNING_LOBBY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)
    assert result.key == "return_lobby"
    assert result.clicked is True
    assert machine.loops == 1


def test_returning_lobby_play_recovery_increments_loop(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    def fake_find_checked(frame, key, tpl, find):
        if key == "play":
            return (100, 600), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"play": dummy_tpl, "return_lobby": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.RETURNING_LOBBY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)
    assert result.key == "play"
    assert result.clicked is True
    assert machine.loops == 1
    assert machine.state is State.A_LOADING


def test_numpy_array_template_truth_value_safe():
    templates = {
        "pirate_token": np.zeros((20, 20, 3), dtype=np.uint8),
        "treasure_reward_banner": None,
        "treasure_reward": None,
    }
    # This must not throw "ValueError: The truth value of an array with more than one element is ambiguous"
    ttpl = templates.get("pirate_token")
    if ttpl is None:
        ttpl = templates.get("treasure_reward_banner")
    if ttpl is None:
        ttpl = templates.get("treasure_reward")
    assert ttpl is not None


def test_in_match_hud_blocks_continue_click(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    def fake_find_checked(frame, key, tpl, find):
        if key == "hud":
            return (150, 950), 0.95
        if key == "continue":
            return (800, 600), 0.90
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"hud": dummy_tpl, "continue": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)
    # Because HUD is visible, match must NOT transition or click continue
    assert result.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []


def test_hud_heals_searching_play_and_skipping_result_to_in_match(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    def fake_find_checked(frame, key, tpl, find):
        if key == "hud":
            return (150, 950), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"hud": dummy_tpl, "play": dummy_tpl, "continue": dummy_tpl, "skip": dummy_tpl}
    
    # Test recovery from SEARCHING_PLAY
    machine = StateMachine(settings, templates, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = machine.step(frame)
    assert machine.state is State.IN_MATCH

    # Test recovery from SKIPPING_RESULT
    machine.state = State.SKIPPING_RESULT
    result = machine.step(frame)
    assert machine.state is State.IN_MATCH

    # Test recovery from RETURNING_LOBBY
    machine.state = State.RETURNING_LOBBY
    result = machine.step(frame)
    assert machine.state is State.IN_MATCH


def test_autocalibrator_never_adapts_continue_or_in_match():
    from types import SimpleNamespace
    from autocal import AutoCalibrator

    settings = SimpleNamespace(auto_calibrate=True)
    cal = AutoCalibrator(settings)
    
    # Must not adapt continue
    cal.adapted["continue"] = 0.70
    assert cal.threshold_for("continue", 0.82) == 0.82
    assert cal.threshold_for("hud", 0.85) == 0.85

    # Attempt must reject key == continue or state == IN_MATCH
    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    res = cal.attempt(
        State.IN_MATCH,
        frame,
        "continue",
        dummy_tpl,
        score=0.74,
        base=0.82,
        ox=0,
        oy=0,
        click=lambda x, y: True,
        scales=(1.0,),
    )
    assert res is False


def test_searching_play_does_not_click_continue(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    def fake_find_checked(frame, key, tpl, find):
        if key == "continue":
            return (800, 600), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"continue": dummy_tpl, "play": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)
    # Must not click continue in SEARCHING_PLAY (lobby)
    assert result.clicked is False
    assert controller.clicks == []


def test_black_screen_death_and_reboot_stays_in_match(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    state_vis = {"hud": False, "continue": False}

    def fake_find_checked(frame, key, tpl, find):
        if state_vis.get(key):
            return (500, 500), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"hud": dummy_tpl, "continue": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Frame 1: Player dies, black screen appears (HUD gone, continue not there)
    r1 = machine.step(frame)
    assert r1.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []
    assert "waiting continue / reboot" in r1.note

    # Frame 2: Screen stays black waiting for reboot
    r2 = machine.step(frame)
    assert r2.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []

    # Frame 3: Teammate reboots, HUD is back!
    state_vis["hud"] = True
    r3 = machine.step(frame)
    assert r3.clicked is False
    assert machine.state is State.IN_MATCH
    assert "match in progress" in r3.note
    assert controller.clicks == []


def test_continue_requires_multi_frame_confirmation(monkeypatch):
    from types import SimpleNamespace
    import state_machine

    settings = SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )

    class FakeController:
        def __init__(self):
            self.clicks = []
        def ready(self):
            return True
        def click(self, x, y):
            self.clicks.append((x, y))
            return True

    state_vis = {"hud": False, "continue": True}

    def fake_find_checked(frame, key, tpl, find):
        if state_vis.get(key):
            return (800, 600), 0.95
        return None, 0.0

    dummy_tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = FakeController()
    templates = {"hud": dummy_tpl, "continue": dummy_tpl}
    machine = StateMachine(settings, templates, controller)
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Frame 1: Continue button appears for the first time
    r1 = machine.step(frame)
    assert r1.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []
    assert "confirming continue (1/2)" in r1.note

    # Frame 2: Continue button is still there (second consecutive frame)
    r2 = machine.step(frame)
    assert r2.clicked is True
    assert machine.state is State.SKIPPING_RESULT
    assert controller.clicks == [(800, 600)]
    assert r2.key == "continue"



