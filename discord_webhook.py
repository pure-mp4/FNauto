from __future__ import annotations

import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from typing import Callable, Mapping, Optional

from redact import redact
from version import APP_VERSION

OK = "ok"
NO_URL = "no_url"
INVALID_URL = "invalid_url"
BAD_REQUEST = "bad_request"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
RATE_LIMITED = "rate_limited"
SERVER = "server"
NETWORK = "network"
NETWORK_DNS = "network_dns"
NETWORK_TLS = "network_tls"
NETWORK_TIMEOUT = "network_timeout"
NETWORK_BLOCKED = "network_blocked"

_ALLOWED_HOSTS = {
    "discord.com",
    "discordapp.com",
    "ptb.discord.com",
    "canary.discord.com",
    "ptb.discordapp.com",
    "canary.discordapp.com",
}
_MAX_RETRIES = 3
_ALERT_WINDOW_S = 600.0
_HTTP_TIMEOUT_S = 15.0
_MIN_SUMMARY_ACTIONS = 5
_WINDOW_S = 60.0

_UA = f"FNauto/{APP_VERSION}"


def valid_webhook(url) -> bool:
    if not isinstance(url, str):
        return False
    value = url.strip()
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or port not in (None, 443):
        return False
    if parsed.query or parsed.fragment:
        return False
    parts = parsed.path.split("/")
    return (
        len(parts) == 5
        and parts[1] == "api"
        and parts[2] == "webhooks"
        and parts[3].isdigit()
        and bool(parts[4])
        and all(c.isalnum() or c in "._-" for c in parts[4])
    )


def _get(settings, key, default=None):
    try:
        if hasattr(settings, "get"):
            return settings.get(key, default)
        return getattr(settings, key, default)
    except Exception:
        return default


def _status_error(status: int) -> str:
    if status == 400:
        return BAD_REQUEST
    if status == 401:
        return UNAUTHORIZED
    if status == 403:
        return FORBIDDEN
    if status == 404:
        return NOT_FOUND
    if status == 429:
        return RATE_LIMITED
    return SERVER


def classify_error(error: BaseException) -> str:
    reason = getattr(error, "reason", None)
    if not isinstance(reason, BaseException):
        reason = error
    if isinstance(reason, socket.gaierror):
        return NETWORK_DNS
    if isinstance(reason, ssl.SSLError) or "certificate" in str(reason).lower():
        return NETWORK_TLS
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
        return NETWORK_TIMEOUT
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError, PermissionError)):
        return NETWORK_BLOCKED
    return NETWORK


def _headers(headers) -> dict:
    if not headers:
        return {}
    try:
        return {str(k).lower(): str(v) for k, v in headers.items()}
    except Exception:
        return {}


def default_transport(url: str, data: bytes, headers: Mapping[str, str], timeout: float = _HTTP_TIMEOUT_S):
    req = urllib.request.Request(url, data=data, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200), _headers(response.headers), response.read(65536)
    except urllib.error.HTTPError as error:
        try:
            body = error.read(65536)
        except Exception:
            body = b""
        return int(error.code), _headers(error.headers), body


def _json_request(payload: dict) -> tuple[bytes, dict]:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return data, {"Content-Type": "application/json", "User-Agent": _UA, "Accept": "application/json"}


def _multipart_request(payload: dict, jpeg: bytes) -> tuple[bytes, dict, str]:
    boundary = "----FNauto" + uuid.uuid4().hex
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="payload_json"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    body.extend(f"\r\n--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="files[0]"; filename="reward.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(jpeg)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return (
        bytes(body),
        {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": _UA,
            "Accept": "application/json",
        },
        boundary,
    )


class DiscordReporter:
    def __init__(
        self,
        settings,
        transport=None,
        sync: bool = False,
        log: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self._transport = transport or default_transport
        self._sync = bool(sync)
        self.log = log or (lambda _message: None)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._threads = []
        self._window = deque()
        self._modes = set()
        self._last_alert = {}
        self._last_report = clock()
        self._sent = True
        self._begin = clock()
        self._session_started = 0.0
        self.total_actions = 0
        self.peak_apm = 0
        self.popups = 0
        self.loops = 0
        self.claims = 0
        self.mode = "A"
        self.lang = "en"

    @property
    def webhook(self) -> str:
        value = _get(self.settings, "discord_webhook_url", "")
        return value.strip() if isinstance(value, str) else ""

    @property
    def configured(self) -> bool:
        return valid_webhook(self.webhook)

    def begin_session(self, mode: str = "A", lang: str = "en") -> None:
        with self._lock:
            self._last_report = self._clock()
            self._begin = self._clock()
            self._session_started = time.time()
            self._window.clear()
            self._modes = {str(mode or "A")}
            self.mode = str(mode or "A")
            self.lang = str(lang or "en")
            self.total_actions = 0
            self.peak_apm = 0
            self.popups = 0
            self.loops = 0
            self.claims = 0
            self._sent = False

    def record_action(self, popup: bool = False) -> None:
        now = self._clock()
        with self._lock:
            self.total_actions += 1
            if popup:
                self.popups += 1
            self._window.append(now)
            cutoff = now - _WINDOW_S
            while self._window and self._window[0] <= cutoff:
                self._window.popleft()
            self.peak_apm = max(self.peak_apm, len(self._window))

    def set_loops(self, value: int) -> None:
        self.loops = int(value)

    def set_claims(self, value: int) -> None:
        self.claims = int(value)

    def set_popups(self, value: int) -> None:
        self.popups = int(value)

    def set_mode(self, mode: str) -> None:
        self.mode = str(mode or "A")
        self._modes.add(self.mode)

    def snapshot(self) -> dict:
        duration = int(max(0.0, self._clock() - self._begin))
        matches_per_min = round(self.loops * 60.0 / duration, 2) if duration > 0 else 0.0
        return {
            "duration_s": duration,
            "runtime": _duration_text(duration),
            "total_actions": self.total_actions,
            "peak_apm": self.peak_apm,
            "loops": self.loops,
            "matches_per_min": matches_per_min,
            "popups": self.popups,
            "claims": self.claims,
            "mode": "+".join(sorted(self._modes)) or self.mode,
            "lang": self.lang,
        }

    def _spawn(self, work: Callable[[], None]) -> Optional[threading.Thread]:
        if self._sync:
            work()
            return None
        thread = threading.Thread(target=work, daemon=True, name="FNauto-discord-webhook")
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()
        return thread

    def _embed_payload(self, title: str, fields: dict, description: str = "", color: int = 0x2F6FED) -> dict:
        payload = {
            "username": "FNauto",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": str(title),
                    "color": int(color),
                    "fields": [
                        {"name": str(name), "value": str(value), "inline": True} for name, value in fields.items()
                    ],
                }
            ],
        }
        if description:
            payload["embeds"][0]["description"] = str(description)[:2000]
        return payload

    def _stats_fields(self) -> dict:
        stats = self.snapshot()
        return {
            "Runtime": stats["runtime"],
            "Laps": stats["loops"],
            "Loop mode": stats["mode"],
            "Matches/min": stats["matches_per_min"],
            "Actions": stats["total_actions"],
            "Peak APM": stats["peak_apm"],
            "Claims": stats["claims"],
        }

    def _post(self, payload: dict, jpeg: Optional[bytes] = None) -> str:
        url = self.webhook
        if not url:
            return NO_URL
        if not valid_webhook(url):
            return INVALID_URL
        if jpeg is None:
            body, headers = _json_request(payload)
        else:
            body, headers, _boundary = _multipart_request(payload, jpeg)
        last = SERVER
        for attempt in range(_MAX_RETRIES + 1):
            try:
                status, response_headers, response_body = self._transport(url, body, headers)
            except Exception as error:
                last = classify_error(error)
                self.log(f"discord webhook: {type(error).__name__} ({last})")
                return last
            if 200 <= int(status) < 300:
                return OK
            last = _status_error(int(status))
            if int(status) == 429 and attempt < _MAX_RETRIES:
                value = _headers(response_headers).get("retry-after", "")
                try:
                    wait = float(value)
                except (TypeError, ValueError):
                    wait = float(2**attempt)
                self._sleep(max(0.0, min(wait, 30.0)))
                continue
            detail = ""
            try:
                detail = response_body.decode("utf-8", "replace")[:120]
            except Exception:
                detail = ""
            self.log(f"discord webhook: HTTP {int(status)} ({last}){(' ' + redact(detail)) if detail else ''}")
            return last
        return RATE_LIMITED

    def _deliver(self, payload: dict, callback, jpeg: Optional[bytes] = None) -> None:
        status = self._post(payload, jpeg)
        if status != OK:
            self.log(f"discord webhook: not delivered ({status})")
        if callback:
            try:
                callback(status)
            except Exception:
                pass

    def _queue(self, payload: dict, callback=None, jpeg: Optional[bytes] = None):
        if not self.webhook:
            if callback:
                callback(NO_URL)
            return None
        if not self.configured:
            if callback:
                callback(INVALID_URL)
            return None
        return self._spawn(lambda: self._deliver(payload, callback, jpeg))

    def send_test(self, callback=None):
        return self._queue(
            self._embed_payload(
                "FNauto test message",
                {"Status": "Webhook configured"},
                "If you can read this, FNauto can post to this channel.",
            ),
            callback,
        )

    def send_remote_url(self, url: str, callback=None):
        payload = self._embed_payload(
            "Phone remote URL",
            {"Address": str(url)[:500]},
            "This URL contains an access token. Anyone who has it can control this PC. "
            "Share it only with yourself and stop the remote when finished.",
            color=0xF5A524,
        )
        return self._queue(payload, callback)

    def send_match_completed(
        self,
        match_num: int,
        time_taken: str,
        time_from: str,
        time_to: str,
        callback=None,
    ):
        if not bool(_get(self.settings, "telemetry_enabled", True)) or not self.configured:
            return None
        payload = {
            "username": "FNauto",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": f"Match {match_num} completed",
                    "color": 0x2ED47A,
                    "fields": [
                        {"name": "Time taken", "value": str(time_taken), "inline": True},
                        {"name": "Time from", "value": str(time_from), "inline": True},
                        {"name": "Time to", "value": str(time_to), "inline": True},
                    ],
                }
            ],
        }
        return self._queue(payload, callback)

    def send_session_summary(self, callback=None) -> None:
        if not bool(_get(self.settings, "telemetry_enabled", True)) or not self.configured:
            return None
        if self._sent or self.total_actions < _MIN_SUMMARY_ACTIONS:
            return None
        self._sent = True
        payload = self._embed_payload("Session summary", self._stats_fields())
        return self._spawn(lambda: self._deliver(payload, callback))

    def maybe_send_periodic(self, hours: float, callback=None) -> None:
        if not bool(_get(self.settings, "telemetry_enabled", True)) or not self.configured or self._sent:
            return None
        try:
            period = float(hours) * 3600.0
        except (TypeError, ValueError):
            return None
        if period <= 0 or self._clock() - self._last_report < period:
            return None
        self._last_report = self._clock()
        payload = self._embed_payload("Progress report", self._stats_fields())
        return self._spawn(lambda: self._deliver(payload, callback))

    def send_alert(self, code: str, detail: str, callback=None) -> None:
        if not bool(_get(self.settings, "alert_enabled", True)) or not self.configured:
            return None
        key = str(code)[:20] or "alert"
        now = self._clock()
        with self._lock:
            last = self._last_alert.get(key)
            if last is not None and now - last < _ALERT_WINDOW_S:
                return None
            self._last_alert[key] = now
        payload = self._embed_payload(
            "FNauto alert",
            {"Type": key, "Detail": str(detail)[:300], "Runtime": self.snapshot()["runtime"]},
            color=0xFF5C6C,
        )
        return self._spawn(lambda: self._deliver(payload, callback))

    def send_stuck(self, state: str, minutes: int, callback=None) -> None:
        return self.send_alert("stuck", f"{state} / {max(0, int(minutes))} min", callback)

    def send_screenshot(self, jpeg: bytes, callback=None) -> None:
        if not bool(_get(self.settings, "reward_shot_enabled", False)):
            return None
        payload = {
            "username": "FNauto",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": "Reward screen",
                    "color": 0x2ED47A,
                    "image": {"url": "attachment://reward.jpg"},
                }
            ],
        }
        return self._queue(payload, callback, bytes(jpeg))

    def send_treasure(self, jpeg: bytes, callback=None) -> None:
        if not bool(_get(self.settings, "treasure_shot_enabled", True)):
            return None
        payload = {
            "username": "FNauto",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": "Treasure Found!",
                    "description": "An in-game treasure reward notification was captured.",
                    "color": 0xFFB800,
                    "image": {"url": "attachment://reward.jpg"},
                }
            ],
        }
        return self._queue(payload, callback, bytes(jpeg))

    def flush(self, timeout: float = 3.0) -> None:
        end = time.monotonic() + timeout
        for thread in list(self._threads):
            left = end - time.monotonic()
            if left <= 0:
                return
            thread.join(left)


def _duration_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"
