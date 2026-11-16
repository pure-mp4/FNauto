from __future__ import annotations

import json

import pytest

from discord_webhook import (
    DiscordReporter,
    classify_error,
    valid_webhook,
)

WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/unit-test-token"
JPEG = b"\xff\xd8\xff\xe0" + b"unit-test-jpeg" * 20 + b"\xff\xd9"


class Store:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class Transport:
    def __init__(self, responses=None):
        self.responses = list(responses or [(204, {}, b"")])
        self.calls = []

    def __call__(self, url, data, headers):
        self.calls.append((url, bytes(data), dict(headers)))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


@pytest.mark.parametrize(
    "url",
    [
        WEBHOOK,
        "https://canary.discord.com/api/webhooks/123456789012345678/unit-test-token",
        "https://discordapp.com/api/webhooks/123456789012345678/unit-test-token",
    ],
)
def test_valid_webhook_accepts_discord_endpoints(url):
    assert valid_webhook(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        WEBHOOK.replace("https://", "http://"),
        WEBHOOK.replace("discord.com", "example.com"),
        "https://discord.com/channels/1/2",
        "https://discord.com/api/webhooks/not-a-number/unit-test-token",
        "https://discord.com:not-a-port/api/webhooks/123456789012345678/unit-test-token",
        WEBHOOK + "?x=1",
        WEBHOOK + "/extra",
    ],
)
def test_valid_webhook_rejects_other_urls(url):
    assert not valid_webhook(url)


def test_empty_webhook_sends_nothing():
    transport = Transport()
    settings = Store(discord_webhook_url="", telemetry_enabled=True, alert_enabled=True, reward_shot_enabled=True)
    reporter = DiscordReporter(settings, transport=transport, sync=True)
    reporter.send_test()
    reporter.send_alert("stuck", "idle")
    reporter.send_session_summary()
    reporter.send_screenshot(JPEG)
    assert transport.calls == []


def test_session_summary_is_json_with_expected_fields():
    transport = Transport()
    reporter = DiscordReporter(
        Store(discord_webhook_url=WEBHOOK, telemetry_enabled=True), transport=transport, sync=True
    )
    reporter.begin_session("A", "en")
    for _ in range(5):
        reporter.record_action()
    reporter.send_session_summary()
    assert len(transport.calls) == 1
    url, body, headers = transport.calls[0]
    assert url == WEBHOOK
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body)
    assert payload["username"] == "FNauto"
    assert payload["embeds"][0]["title"] == "Session summary"
    assert any(field["name"] == "Actions" for field in payload["embeds"][0]["fields"])


def test_reward_screenshot_is_multipart():
    transport = Transport()
    reporter = DiscordReporter(
        Store(discord_webhook_url=WEBHOOK, reward_shot_enabled=True), transport=transport, sync=True
    )
    reporter.send_screenshot(JPEG)
    assert len(transport.calls) == 1
    _url, body, headers = transport.calls[0]
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="files[0]"' in body
    assert JPEG in body
    assert b'"image":{"url":"attachment://reward.jpg"}' in body


def test_rate_limit_retries_after_retry_after():
    transport = Transport([(429, {"Retry-After": "0"}, b""), (204, {}, b"")])
    sleeps = []
    reporter = DiscordReporter(Store(discord_webhook_url=WEBHOOK), transport=transport, sync=True, sleep=sleeps.append)
    reporter.begin_session()
    for _ in range(5):
        reporter.record_action()
    reporter.send_session_summary()
    assert len(transport.calls) == 2
    assert sleeps == [0.0]


def test_alert_deduplicates_within_window():
    now = [0.0]
    transport = Transport()
    reporter = DiscordReporter(
        Store(discord_webhook_url=WEBHOOK, alert_enabled=True), transport=transport, sync=True, clock=lambda: now[0]
    )
    reporter.send_alert("stuck", "first")
    reporter.send_alert("stuck", "second")
    assert len(transport.calls) == 1
    now[0] = 601.0
    reporter.send_alert("stuck", "third")
    assert len(transport.calls) == 2


def test_error_classification_is_specific():
    assert classify_error(OSError("timed out")) == "network_timeout"
    assert classify_error(PermissionError("denied")) == "network_blocked"
    assert classify_error(ValueError("other")) == "network"
