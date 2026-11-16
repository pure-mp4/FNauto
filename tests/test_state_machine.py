from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import config
import state_machine
import worker
from state_machine import State, StateMachine
from vision import Plate, find_plate, load_template_auto


class Controller:
    def __init__(self):
        self.clicks = []

    def ready(self):
        return True

    def click(self, x, y):
        self.clicks.append((x, y))
        return True


def make_settings():
    return SimpleNamespace(
        threshold=0.82,
        scales=(1.0,),
        auto_calibrate=False,
        mode_fix_enabled=False,
    )


def lobby_frame(label_name=None):
    assets = Path(__file__).resolve().parents[1] / "assets"
    button = cv2.imread(str(assets / "return_lobby_btn_plate.png"), cv2.IMREAD_UNCHANGED)
    frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
    height, width = button.shape[:2]
    x, y = 720, 250
    target = frame[y : y + height, x : x + width]
    alpha = (button[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    target[:] = (button[:, :, :3].astype(np.float32) * alpha + target.astype(np.float32) * (1 - alpha)).astype(np.uint8)
    if label_name is not None:
        label = cv2.imread(str(assets / label_name))
        label_height, label_width = label.shape[:2]
        left = x + (width - label_width) // 2
        top = y + (height - label_height) // 2
        frame[top : top + label_height, left : left + label_width] = label
    return frame


def use_visible(monkeypatch, visible):
    def fake_find_checked(frame, key, tpl, find):
        if key in visible:
            return (100, 200, 0.99), 0.99
        return None, 0.0

    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)


def test_play_waits_for_hud_before_starting_match(monkeypatch):
    visible = {"play"}
    use_visible(monkeypatch, visible)
    controller = Controller()
    machine = StateMachine(make_settings(), {"play": object(), "hud": object()}, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)

    assert result.key == "play"
    assert result.clicked is True
    assert machine.state is State.A_LOADING
    assert controller.clicks == [(100, 200)]

    visible.clear()
    visible.add("hud")
    result = machine.step(frame)

    assert result.note == "match started"
    assert result.clicked is False
    assert machine.state is State.IN_MATCH


def test_mode_a_recovers_return_to_lobby_from_searching_play(monkeypatch):
    visible = {"return_lobby"}
    use_visible(monkeypatch, visible)
    controller = Controller()
    machine = StateMachine(make_settings(), {"return_lobby": object(), "play": object()}, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)

    assert result.key == "return_lobby"
    assert result.clicked is True
    assert machine.state is State.SEARCHING_PLAY
    assert controller.clicks == [(100, 200)]


def test_return_lobby_plate_clicks_only_without_match_hud(monkeypatch):
    visible = {"return_lobby_plate", "return_lobby_text_en"}
    use_visible(monkeypatch, visible)
    controller = Controller()
    machine = StateMachine(
        make_settings(),
        {"return_lobby_plate": object(), "hud": object(), "return_lobby_text_en": object()},
        controller,
    )
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)

    assert result.key == "return_lobby_plate"
    assert result.clicked is True
    assert machine.state is State.SEARCHING_PLAY
    assert controller.clicks == [(100, 200)]


def test_return_lobby_plate_is_blocked_while_match_hud_is_visible(monkeypatch):
    visible = {"return_lobby_plate", "return_lobby_text_en", "hud"}
    use_visible(monkeypatch, visible)
    controller = Controller()
    machine = StateMachine(
        make_settings(),
        {"return_lobby_plate": object(), "hud": object(), "return_lobby_text_en": object()},
        controller,
    )
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)

    assert result.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []


def test_return_lobby_plate_is_not_used_from_searching_play(monkeypatch):
    visible = {"return_lobby_plate"}
    use_visible(monkeypatch, visible)
    controller = Controller()
    machine = StateMachine(make_settings(), {"return_lobby_plate": object(), "hud": object()}, controller)
    machine.state = State.SEARCHING_PLAY
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    result = machine.step(frame)

    assert result.clicked is False
    assert machine.state is State.SEARCHING_PLAY
    assert controller.clicks == []


def test_return_lobby_plate_does_not_click_unrelated_purple_button_inside_roi(monkeypatch):
    assets = Path(__file__).resolve().parents[1] / "assets"
    plate = load_template_auto(
        str(assets / "return_lobby_btn_plate.png"),
        {"roi": config.PLATES["return_lobby"]["roi"], "threshold": 0.84},
    )
    text = load_template_auto(str(assets / "return_lobby_btn_en.png"))
    button = cv2.imread(str(assets / "return_lobby_btn_plate.png"), cv2.IMREAD_UNCHANGED)
    cv2.putText(button, "SHOP", (80, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 20, 80, 255), 3, cv2.LINE_AA)
    frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
    height, width = button.shape[:2]
    x, y = 720, 250
    target = frame[y : y + height, x : x + width]
    alpha = (button[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    target[:] = (button[:, :, :3].astype(np.float32) * alpha + target.astype(np.float32) * (1 - alpha)).astype(np.uint8)

    def fake_find_checked(candidate, key, tpl, find):
        if key == "hud":
            return None, 0.0
        return find(candidate)

    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = Controller()
    machine = StateMachine(
        make_settings(),
        {"return_lobby_plate": plate, "hud": object(), "return_lobby_text_en": text},
        controller,
    )
    machine.state = State.IN_MATCH
    assert find_plate(frame, plate, machine.s.scales)[0] is not None

    result = machine.step(frame)

    assert result.clicked is False
    assert controller.clicks == []


@pytest.mark.parametrize(
    ("lang", "label_name"),
    (("en", "return_lobby_btn_en.png"), ("ja", "return_lobby_btn.png")),
    ids=("en", "ja"),
)
def test_return_lobby_plate_accepts_genuine_localized_label(lang, label_name):
    templates = worker.load_templates(lang)
    templates["return_lobby"] = None
    controller = Controller()
    machine = StateMachine(make_settings(), templates, controller)
    machine.state = State.IN_MATCH
    frame = lobby_frame(label_name)

    result = machine.step(frame)

    assert find_plate(frame, templates["return_lobby_plate"], machine.s.scales)[0] is not None
    assert result.key == "return_lobby_plate"
    assert result.clicked is True
    assert machine.state is State.SEARCHING_PLAY
    assert controller.clicks == [(968, 285)]


@pytest.mark.parametrize("lang", config.PLATE_LANGS)
def test_plate_languages_keep_primary_plate_detection(lang):
    templates = worker.load_templates(lang)
    controller = Controller()
    machine = StateMachine(make_settings(), templates, controller)
    machine.state = State.IN_MATCH

    result = machine.step(lobby_frame())

    assert isinstance(templates["return_lobby"], Plate)
    assert result.key == "return_lobby"
    assert result.clicked is True
    assert machine.state is State.SEARCHING_PLAY
    assert controller.clicks == [(968, 285)]


def test_return_lobby_plate_does_not_click_purple_button_outside_roi(monkeypatch):
    assets = Path(__file__).resolve().parents[1] / "assets"
    plate = load_template_auto(
        str(assets / "return_lobby_btn_plate.png"),
        {"roi": config.PLATES["return_lobby"]["roi"], "threshold": 0.84},
    )
    text = load_template_auto(str(assets / "return_lobby_btn_en.png"))
    button = cv2.imread(str(assets / "return_lobby_btn_plate.png"), cv2.IMREAD_UNCHANGED)
    frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
    height, width = button.shape[:2]
    x, y = 100, 100
    target = frame[y : y + height, x : x + width]
    alpha = (button[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    target[:] = (button[:, :, :3].astype(np.float32) * alpha + target.astype(np.float32) * (1 - alpha)).astype(np.uint8)

    def fake_find_checked(candidate, key, tpl, find):
        if key == "hud":
            return None, 0.0
        return find(candidate)

    monkeypatch.setattr(state_machine, "find_checked", fake_find_checked)
    controller = Controller()
    machine = StateMachine(
        make_settings(),
        {"return_lobby_plate": plate, "hud": object(), "return_lobby_text_en": text},
        controller,
    )
    machine.state = State.IN_MATCH

    result = machine.step(frame)

    assert result.clicked is False
    assert controller.clicks == []


def test_loading_falls_back_without_enabling_afk(monkeypatch):
    visible = set()
    use_visible(monkeypatch, visible)
    clock = [0.0]
    controller = Controller()
    machine = StateMachine(make_settings(), {"hud": object(), "play": object()}, controller, clock=lambda: clock[0])
    machine.state = State.A_LOADING
    machine._loading_since = 0.0
    machine._loading_retry = 0.0
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    clock[0] = 121.0
    visible.add("play")

    result = machine.step(frame)

    assert result.note == "waiting match (no-input fallback)"
    assert result.clicked is False
    assert machine.state is State.A_LOADING
    assert machine._loading_quiet is True
    assert controller.clicks == []

    clock[0] = 130.0
    result = machine.step(frame)

    assert result.clicked is False
    assert machine.state is State.A_LOADING
    assert controller.clicks == []


def test_loading_detects_hud_after_long_queue(monkeypatch):
    visible = set()
    use_visible(monkeypatch, visible)
    clock = [0.0]
    controller = Controller()
    machine = StateMachine(make_settings(), {"hud": object()}, controller, clock=lambda: clock[0])
    machine.state = State.A_LOADING
    machine._loading_since = 0.0
    machine._loading_retry = 0.0
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    clock[0] = 121.0

    first = machine.step(frame)

    assert first.note == "waiting match (no-input fallback)"
    assert machine.state is State.A_LOADING
    assert controller.clicks == []

    visible.add("hud")
    clock[0] = 180.0
    second = machine.step(frame)

    assert second.note == "match started"
    assert second.clicked is False
    assert machine.state is State.IN_MATCH
    assert controller.clicks == []


def test_diagnose_reports_candidate_scores(monkeypatch):
    visible = {"play"}
    use_visible(monkeypatch, visible)
    machine = StateMachine(make_settings(), {"play": object()}, Controller())
    machine.state = State.IN_MATCH
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    scores = machine.diagnose(frame)

    assert scores["play"]["score"] == 0.99
    assert scores["play"]["at"] == [100, 200]
    assert scores["hud"] is None


def test_diagnostic_frame_is_written(tmp_path):
    settings = SimpleNamespace(path=str(tmp_path / "settings.json"))
    frame = np.zeros((32, 48, 3), dtype=np.uint8)

    path = worker.save_diagnostic_frame(frame, settings)

    assert path
    with open(path, "rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"
