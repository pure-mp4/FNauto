from __future__ import annotations

import web_remote
from remote_tools import RemoteBridge


class Store:
    def __init__(self):
        self.values = {"lang": "en", "mode": "A", "web_remote_port": 8765}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def test_tokens_are_random_length_and_alphabet_safe():
    token = web_remote.new_token()
    assert len(token) == 16
    assert set(token) <= set(web_remote.TOKEN_CHARS)
    assert web_remote.new_token() != token


def test_local_client_gate():
    assert web_remote.is_local_client("127.0.0.1")
    assert web_remote.is_local_client("10.1.2.3")
    assert not web_remote.is_local_client("1.1.1.1")
    assert not web_remote.is_local_client("not-an-address")


def test_client_of_marks_tunnel_requests():
    assert web_remote.client_of("127.0.0.1", {"CF-Connecting-IP": "198.51.100.4"}) == ("198.51.100.4", True)
    assert web_remote.client_of("10.1.2.3", {}) == ("10.1.2.3", False)


def test_rendered_page_has_no_removed_controls():
    page = web_remote.render_page("en", "token-value")
    assert "FNauto REMOTE" in page
    assert "token-value" in page
    assert "SMOOTH BIO-MOTION" not in page
    assert "ZERO-SHOT" not in page
    manifest = web_remote.manifest_json("token-value")
    assert "Remote console for FNauto" in manifest
    assert "token-value" in manifest


def test_lockout_after_repeated_failures():
    now = [0.0]
    lockout = web_remote.Lockout(clock=lambda: now[0])
    for _ in range(web_remote.MAX_FAILS):
        lockout.fail("10.1.2.3")
    assert lockout.locked("10.1.2.3") > 0
    now[0] = web_remote.LOCK_S + 1
    assert lockout.locked("10.1.2.3") == 0


def test_remote_bridge_has_no_removed_status_fields():
    bridge = RemoteBridge(Store())
    status = bridge.status()
    assert status["running"] is False
    assert status["mode"] == "A"
    assert "bio" not in status
    assert bridge.action("biomotion")["ok"] is False
    assert bridge.action("unknown") == {"ok": False, "error": "unknown_action"}
