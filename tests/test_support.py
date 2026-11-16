from __future__ import annotations

import app_support
from redact import redact
from version import APP_VERSION


def test_window_position_centres_first_run():
    assert app_support.window_position(-1, -1, 800, 600, (0, 0, 1920, 1080)) == (560, 160)


def test_window_position_is_clamped_to_screen():
    assert app_support.clamp_geometry(-50, 2000, 800, 600, (0, 0, 1920, 1080)) == (0, 480)
    assert app_support.window_position(5000, 5000, 800, 600, (0, 0, 1920, 1080)) == (1120, 480)


def test_file_logger_redacts_credentials(tmp_path):
    path = tmp_path / "FNauto.log"
    logger = app_support.FileLogger(str(path))
    logger.write("failed https://discord.com/api/webhooks/123456789012345678/secret-token")
    text = path.read_text(encoding="utf-8")
    assert "secret-token" not in text
    assert "https://discord.com/api/webhooks/[redacted]/[redacted]" in text


def test_redact_handles_phone_token_and_case_insensitive_webhook():
    text = redact("HTTPS://DISCORD.COM:443/api/webhooks/123/token?token=abc123")
    assert "123/token" not in text
    assert "abc123" not in text
    assert "[redacted]" in text


def test_taskbar_icon_is_optional_without_a_window():
    assert app_support.apply_taskbar_icon(0) == []


def test_version_is_nonempty():
    assert APP_VERSION
