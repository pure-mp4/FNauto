from __future__ import annotations

import threading
import time
from types import SimpleNamespace
import numpy as np
import pytest

from anti_afk import AntiAfk


def test_human_movement_cycle():
    events = []
    current_time = [100.0]

    def fake_down(key: str):
        events.append((current_time[0], "down", key))

    def fake_up(key: str):
        events.append((current_time[0], "up", key))

    def fake_clock():
        return current_time[0]

    settings = SimpleNamespace(
        movement_profile="continuous",
        afk_enabled=True,
        sprint_enabled=True,
        sprint_interval_s=3.0,
        sprint_hold_s=15.0,
        jump_stride_enabled=True,
        jump_stride_interval_s=5.0,
        afk_keys=("w", "a", "s", "d"),
        afk_mouse_look=False,
    )

    afk = AntiAfk(
        settings,
        active=lambda: True,
        key_down=fake_down,
        key_up=fake_up,
        clock=fake_clock,
    )

    stop = threading.Event()

    # Run for simulated 25 seconds by ticking through in a thread
    def runner():
        afk._run_continuous(stop)

    t = threading.Thread(target=runner)
    t.start()

    # Step through time to trigger:
    # 1. Walk phase (t = 100 to 103)
    # 2. Sprint phase (t = 103 to 118)
    # 3. Weaves and Jumps
    for _ in range(140):
        time.sleep(0.005)
        current_time[0] += 0.35

    stop.set()
    t.join(timeout=2.0)

    # Verify W was pressed and held down
    w_downs = [e for e in events if e[1] == "down" and e[2] == "w"]
    assert len(w_downs) >= 1

    # Verify Shift was pressed for tactical sprint
    shift_downs = [e for e in events if e[1] == "down" and e[2] == "shift"]
    assert len(shift_downs) >= 1

    # Verify Space was pressed for fluid jump hop
    space_downs = [e for e in events if e[1] == "down" and e[2] == "space"]
    assert len(space_downs) >= 1

    # Verify A or D was pressed for lateral weave
    weave_downs = [e for e in events if e[1] == "down" and e[2] in ("a", "d")]
    assert len(weave_downs) >= 1

    # Verify all keys were released on stop
    last_events = events[-6:]
    released_keys = {e[2] for e in last_events if e[1] == "up"}
    assert "w" in released_keys


def test_camera_turning_0_to_90_degrees():
    looks = []
    def fake_look(dx, dy, duration_ms):
        looks.append((dx, dy, duration_ms))

    settings = SimpleNamespace(
        movement_profile="continuous",
        afk_enabled=True,
        afk_mouse_look=True,
    )
    afk = AntiAfk(settings, active=lambda: True, look=fake_look)

    # Test explicit 90 degree turn
    afk._turn_camera(90.0)
    assert len(looks) == 1
    dx, dy, ms = looks[0]
    # 90 degrees corresponds to approx 560-700 px (doubled)
    assert 500 <= dx <= 720
    # dy vertical pitch must be subtle (between -6 and +6)
    assert -6 <= dy <= 6
    assert 160 <= ms <= 550

    # Test random turn: angle clamped within 0-90 degrees
    for _ in range(10):
        afk._turn_camera(0.0)
    for dx, dy, ms in looks[1:]:
        assert abs(dx) <= 720
        assert -6 <= dy <= 6


def test_w_key_heartbeat_reassertion():
    events = []
    current_time = [10.0]

    def fake_down(key: str):
        events.append((current_time[0], "down", key))

    def fake_up(key: str):
        events.append((current_time[0], "up", key))

    settings = SimpleNamespace(
        movement_profile="continuous",
        afk_enabled=True,
        sprint_enabled=True,
        sprint_interval_s=3.0,
        sprint_hold_s=15.0,
        jump_stride_enabled=False,
        afk_keys=("w", "a", "s", "d"),
        afk_mouse_look=False,
    )

    afk = AntiAfk(
        settings,
        active=lambda: True,
        key_down=fake_down,
        key_up=fake_up,
        clock=lambda: current_time[0],
    )

    stop = threading.Event()
    t = threading.Thread(target=lambda: afk._run_continuous(stop))
    t.start()

    # Simulate 8 seconds ticking through
    for _ in range(40):
        time.sleep(0.005)
        current_time[0] += 0.2

    stop.set()
    t.join(timeout=2.0)

    # W must be re-asserted multiple times across the session via heartbeat
    w_downs = [e for e in events if e[1] == "down" and e[2] == "w"]
    assert len(w_downs) >= 5, "W key must be repeatedly re-asserted via heartbeat to survive player reboot/flushes"


def test_emote_button_rejected_as_claim():
    from state_machine import State, StateMachine, is_valid_claim_position

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Emote button is on the bottom right (e.g. x=1150, y=650)
    emote_match = (1150, 650, 0.95)
    assert not is_valid_claim_position(frame, "claim", emote_match)
    assert not is_valid_claim_position(frame, "claim_single", emote_match)

    # Claim buttons are horizontally centered in the lower area (e.g. x=640, y=600)
    center_claim_match = (640, 600, 0.95)
    assert is_valid_claim_position(frame, "claim", center_claim_match)
    assert is_valid_claim_position(frame, "claim_single", center_claim_match)


def test_w_key_release_gap_cycle():
    events = []
    current_time = [10.0]

    def fake_down(key: str):
        events.append((current_time[0], "down", key))

    def fake_up(key: str):
        events.append((current_time[0], "up", key))

    settings = SimpleNamespace(
        movement_profile="continuous",
        afk_enabled=True,
        sprint_enabled=True,
        sprint_interval_s=3.0,
        sprint_hold_s=15.0,
        jump_stride_enabled=False,
        afk_keys=("w", "a", "s", "d"),
        afk_mouse_look=False,
    )

    afk = AntiAfk(
        settings,
        active=lambda: True,
        key_down=fake_down,
        key_up=fake_up,
        clock=lambda: current_time[0],
    )

    stop = threading.Event()
    t = threading.Thread(target=lambda: afk._run_continuous(stop))
    t.start()

    # Step through 24 seconds to trigger the 15-20s pause cycle
    for _ in range(70):
        time.sleep(0.005)
        current_time[0] += 0.35

    stop.set()
    t.join(timeout=2.0)

    # Verify W had clean up and down transitions across the cycle
    w_ups = [e for e in events if e[1] == "up" and e[2] == "w"]
    w_downs = [e for e in events if e[1] == "down" and e[2] == "w"]
    assert len(w_ups) >= 1, "W must experience a clean 2s release gap every 15-20s"
    assert len(w_downs) >= len(w_ups), "W must resume after release gap"


def test_pirate_token_template_exists():
    import config, os, cv2
    tpl_path = config.template_path("pirate_token")
    assert os.path.exists(tpl_path), f"Pirate token template missing at {tpl_path}"
    img = cv2.imread(tpl_path)
    assert img is not None, "Failed to load pirate token template image"
    assert img.shape[0] > 20 and img.shape[1] > 20


