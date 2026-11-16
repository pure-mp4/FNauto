from __future__ import annotations

import sys
import threading
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import app_support
import qt_app as Q


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    Q.load_fonts()
    return app


@pytest.fixture
def crash_guard(qapp, tmp_path):
    events = []
    old_sys, old_thread = sys.excepthook, threading.excepthook
    app_support.install_excepthook(
        app_support.FileLogger(str(tmp_path / "q1.log")),
        notify=lambda message: events.append(message),
    )

    def log_notice(message):
        if "Something went wrong" in str(message):
            events.append(str(message))

    yield log_notice
    sys.excepthook, threading.excepthook = old_sys, old_thread
    assert not events, f"exception hook / Log notice fired: {events[:3]}"


@pytest.fixture
def shell(qapp, crash_guard):
    theme = Q.Theme()
    settings = Q.Settings()
    sh = Q.Shell(theme, settings)
    sh.signals.log_line.connect(crash_guard)
    sh.show()
    QTest.qWait(120)
    yield sh
    sh.close()
    QTest.qWait(30)


def test_quit_icon_has_a_rail_center(shell):
    assert shell.rail.icon_center("quit") == shell.rail.quit_center()
    for name in Q.ICON_NAMES:
        point = shell.rail.icon_center(name)
        assert 0 <= point.x() < shell.rail.width()
        assert 0 <= point.y() < shell.rail.height()


def test_hover_quit_tooltip_never_raises(shell):
    shell._rail_hover("quit")
    QTest.qWait(450)
    QApplication.processEvents()
    assert shell.tip_name == "quit"
    assert shell.tip.isVisible()
    shell.tip.hide()
    shell._rail_hover("")


def test_fresh_settings_and_window_are_opaque(qapp):
    settings = Q.Settings()
    sh = Q.Shell(Q.Theme(), settings)
    sh.show()
    QTest.qWait(120)
    try:
        assert settings.get("ui_opacity") == 1.0
        assert sh.windowOpacity() == 1.0
        image = sh.grab().toImage()
        center = image.pixelColor(image.width() // 2, image.height() // 2)
        assert center.alpha() == 255
    finally:
        sh.close()
        QTest.qWait(20)


def test_loop_notifications_use_i18n_copy_and_available_detail(shell):
    shell.settings.set("mode", "A")
    shell._run_started = time.monotonic() - 843
    shell.home.values["laps"].setText("12")
    shell._notify(
        Q.TR.t("notif_loop_stopped"),
        "info",
        detail=shell._loop_stop_detail(),
    )
    entry = shell.notes.entry_widgets[0]
    assert entry.title_text == Q.TR.t("notif_loop_stopped")
    assert entry.detail_text == "Mode A · 12 laps · 14m 03s"


def test_notification_cards_are_compact_and_content_sized(shell):
    notes = shell.notes
    notes.notes.clear()
    notes.add_note("Loop started", "success")
    entry = notes.entry_widgets[0]
    assert 52 <= entry.height() <= 64
    assert entry.meta_rect.top() - entry.title_rect.bottom() <= 6
    assert entry.copy.height() == 28
    assert entry.copy.y() == (entry.height() - 28) // 2
    assert notes.entry_layout.contentsMargins().top() == 8
    assert notes.entry_layout.contentsMargins().right() == 6
    assert notes.entry_layout.spacing() == 8

    notes.notes.clear()
    for i in range(30):
        notes.add_note(f"Loop started\nMode A · {i} laps", "success")
    assert len(notes.entry_widgets) == 30
    assert 170 <= notes.height() <= 440
    assert notes.scroll.verticalScrollBar().value() == 0
    assert notes.entry_widgets[0].note[1].startswith("Loop started")

    notes.notes.clear()
    long_detail = "A very long detail " * 40
    notes.add_note("Saved link\n" + long_detail, "info")
    entry = notes.entry_widgets[0]
    assert entry.detail_lines <= 3
    assert entry.detail_elided
    assert entry.height() <= 110
    assert entry.title_rect.right() <= entry.copy.x()


def test_notification_layout_in_all_six_languages(shell):
    notes = shell.notes
    for lang in ("en", "ja", "es", "pt", "ru", "fr"):
        Q.TR.set_lang(lang)
        notes.notes.clear()
        notes.add_note(Q.TR.t("notif_loop_started") + "\n" + Q.TR.t("notif_mode_detail", mode="A"), "success")
        entry = notes.entry_widgets[0]
        assert entry.title_text == Q.TR.t("notif_loop_started")
        assert entry.detail_text == Q.TR.t("notif_mode_detail", mode="A")
        assert 52 <= entry.height() <= 80
        assert entry.meta_rect.top() - entry.title_rect.bottom() <= 24
        assert notes.entry_layout.contentsMargins().right() == 6
