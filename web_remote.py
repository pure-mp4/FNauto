import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

from web_page import PAGE

TOKEN_CHARS = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_BODY = 1024
PORT_TRIES = 10
MAX_FAILS = 5
LOCK_S = 300.0
APP_NAME, APP_SHORT, APP_COLOR = ("FNauto REMOTE", "FNauto", "#09090B")


class LatestFrame:
    def __init__(self, max_w: int = 720, quality: int = 55):
        self._frame = None
        self._jpeg, self._jpeg_t, self._jpeg_for = (None, 0.0, None)
        self._lock = threading.Lock()
        self.max_w, self.quality = (max_w, quality)

    def put(self, frame) -> None:
        self._frame = frame

    def clear(self) -> None:
        self._frame = None

    def jpeg(self) -> Optional[bytes]:
        frame = self._frame
        if frame is None:
            return None
        with self._lock:
            if self._jpeg is not None and self._jpeg_for is frame and (time.monotonic() - self._jpeg_t < 1.5):
                return self._jpeg
            try:
                import cv2

                h, w = frame.shape[:2]
                if w > self.max_w:
                    frame = cv2.resize(
                        frame, (self.max_w, max(1, int(h * self.max_w / w))), interpolation=cv2.INTER_AREA
                    )
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                data = buf.tobytes() if ok else None
            except Exception:
                data = None
            self._jpeg, self._jpeg_t, self._jpeg_for = (data, time.monotonic(), self._frame)
            return data


LATEST = LatestFrame()


def new_token(n: int = 16) -> str:
    return "".join((secrets.choice(TOKEN_CHARS) for _ in range(n)))


def lan_ip() -> str:
    try:
        for target in (("10.255.255.255", 1), ("192.168.255.255", 1), ("172.31.255.255", 1)):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
                    sk.connect(target)
                    ip = sk.getsockname()[0]
                if ip and (not ip.startswith("127.")):
                    return ip
            except OSError:
                continue
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def is_local_client(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def render_page(lang: str, token: str = "") -> str:
    return PAGE.replace("__LANG__", lang if lang.isalpha() else "en").replace(
        "__QS__", "?token=" + quote(token, safe="")
    )


def manifest_json(token: str) -> str:
    qs = "?token=" + quote(token, safe="")
    return json.dumps(
        {
            "name": APP_NAME,
            "short_name": APP_SHORT,
            "description": "Remote console for FNauto",
            "start_url": "/" + qs,
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": APP_COLOR,
            "theme_color": APP_COLOR,
            "icons": [
                {"src": f"/icon-{n}.png{qs}", "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"}
                for n in (192, 512)
            ]
            + [{"src": "/icon.svg" + qs, "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
        },
        ensure_ascii=False,
    )


def icon_svg() -> str:
    c = "stroke='#F4F4F6' stroke-width='6' fill='none' stroke-linecap='square'"
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 128'><rect width='128' height='128' fill='#09090B'/><path d='M38 54V38h16M90 54V38H74M38 74v16h16M90 74v16H74' {c}/><rect x='60' y='60' width='8' height='8' fill='#10B981'/></svg>"


def icon_png(size: int) -> Optional[bytes]:
    try:
        import cv2
        import numpy as np

        img = np.full((size, size, 3), (11, 9, 9), np.uint8)
        u = size / 128.0

        def p(v):
            return int(round(v * u))

        t = max(2, p(6))
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx, cy = (p(64 + sx * 26), p(64 + sy * 26))
            cv2.line(img, (cx, cy), (cx, cy - sy * p(16)), (246, 244, 244), t)
            cv2.line(img, (cx, cy), (cx - sx * p(16), cy), (246, 244, 244), t)
        cv2.rectangle(img, (p(60), p(60)), (p(68), p(68)), (129, 185, 16), -1)
        ok, buf = cv2.imencode(".png", img)
        return buf.tobytes() if ok else None
    except Exception:
        return None


class Lockout:
    def __init__(self, max_fails: int = MAX_FAILS, lock_s: float = LOCK_S, clock=time.monotonic, cap: int = 1000):
        self.max_fails, self.lock_s, self._clock, self.cap = (max_fails, lock_s, clock, cap)
        self._fails = {}
        self._until = {}
        self._mu = threading.Lock()

    def locked(self, who: str) -> float:
        with self._mu:
            left = self._until.get(who, 0.0) - self._clock()
            if left <= 0:
                self._until.pop(who, None)
                return 0.0
            return left

    def fail(self, who: str) -> None:
        with self._mu:
            if len(self._fails) >= self.cap:
                self._fails.clear()
            n = self._fails.get(who, 0) + 1
            if n >= self.max_fails:
                self._until[who] = self._clock() + self.lock_s
                n = 0
            self._fails[who] = n

    def ok(self, who: str) -> None:
        with self._mu:
            self._fails.pop(who, None)


def client_of(peer: str, headers) -> Tuple[str, bool]:
    real = (headers.get("CF-Connecting-IP") or "").strip()
    try:
        loop = ipaddress.ip_address(peer.split("%")[0]).is_loopback
    except ValueError:
        loop = False
    if loop and real:
        return (real[:64], True)
    return (peer, False)


class WebRemote:
    def __init__(self, bridge, port: int = 8765, token: str = "", host: str = "0.0.0.0"):
        self.bridge, self.port, self.host = (bridge, int(port), host)
        self.token = token or new_token()
        self._srv = None
        self._thread = None
        self.allow_public = False
        self.lockout = Lockout()

    @property
    def running(self) -> bool:
        return self._srv is not None

    def set_public(self, allowed: bool) -> None:
        self.allow_public = bool(allowed)

    def url(self, ip: str = "") -> str:
        return f"http://{ip or lan_ip()}:{self.port}/?token={self.token}"

    def start(self) -> bool:
        if self._srv is not None:
            return True
        self.token = new_token()
        remote = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 5
            protocol_version = "HTTP/1.0"

            def log_message(self, *_a):
                return

            def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _auth(self) -> Optional[str]:
                who, tunnel = client_of(self.client_address[0], self.headers)
                if tunnel:
                    if not remote.allow_public:
                        self._send(403, b"forbidden")
                        return None
                elif not is_local_client(who):
                    self._send(403, b"forbidden")
                    return None
                wait = remote.lockout.locked(who)
                if wait > 0:
                    self.send_response(429)
                    self.send_header("Retry-After", str(int(wait) + 1))
                    self.send_header("Content-Length", "6")
                    self.end_headers()
                    self.wfile.write(b"locked")
                    return None
                u = urlparse(self.path)
                got = (parse_qs(u.query).get("token") or [""])[0] or self.headers.get("X-Token", "")
                if not hmac.compare_digest(got.encode(), remote.token.encode()):
                    remote.lockout.fail(who)
                    self._send(403, b"forbidden")
                    return None
                remote.lockout.ok(who)
                return u.path

            def do_GET(self) -> None:
                path = self._auth()
                if path is None:
                    return
                try:
                    if path == "/":
                        self._send(
                            200,
                            render_page(remote.bridge.labels().get("lang", "en"), remote.token).encode("utf-8"),
                            "text/html; charset=utf-8",
                        )
                        return
                    if path == "/manifest.json":
                        self._send(200, manifest_json(remote.token).encode("utf-8"), "application/manifest+json")
                        return
                    if path == "/icon.svg":
                        self._send(200, icon_svg().encode("utf-8"), "image/svg+xml")
                        return
                    if path in ("/icon-180.png", "/icon-192.png", "/icon-512.png"):
                        data = icon_png(int(path[6:9]))
                        if data:
                            self._send(200, data, "image/png")
                            return
                        self._send(404, b"no icon")
                        return
                    if path == "/api/status":
                        self._send(
                            200,
                            json.dumps(remote.bridge.status(), ensure_ascii=False).encode("utf-8"),
                            "application/json",
                        )
                        return
                    if path == "/api/frame.jpg":
                        data = remote.bridge.frame_jpeg()
                        if data:
                            self._send(200, data, "image/jpeg")
                            return
                        self._send(404, b"no frame")
                        return
                    self._send(404, b"not found")
                except Exception:
                    self._send(500, b"error")

            do_HEAD = do_GET

            def do_POST(self) -> None:
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = 0
                raw = self.rfile.read(min(max(n, 0), 65536)) if n > 0 else b""
                path = self._auth()
                if path is None:
                    return
                if path == "/api/relaunch":
                    try:
                        out = remote.bridge.action("relaunch", "")
                        self._send(200, json.dumps(out).encode(), "application/json")
                        return
                    except Exception:
                        self._send(400, json.dumps({"ok": False, "error": "bad_request"}).encode(), "application/json")
                        return
                if path != "/api/action":
                    self._send(404, b"not found")
                    return
                try:
                    if n <= 0 or n > MAX_BODY:
                        self._send(413, json.dumps({"ok": False, "error": "too_large"}).encode(), "application/json")
                        return
                    body = json.loads(raw.decode("utf-8"))
                    out = (
                        remote.bridge.action(str(body.get("action", "")), str(body.get("value", "")))
                        if isinstance(body, dict)
                        else {"ok": False, "error": "bad_request"}
                    )
                    self._send(200, json.dumps(out).encode(), "application/json")
                except Exception:
                    self._send(400, json.dumps({"ok": False, "error": "bad_request"}).encode(), "application/json")

        for port in range(self.port, self.port + PORT_TRIES):
            try:
                self._srv = ThreadingHTTPServer((self.host, port), Handler)
                self.port = port
                break
            except OSError:
                continue
        if self._srv is None:
            return False
        self._srv.daemon_threads = True
        self._thread = threading.Thread(
            target=self._srv.serve_forever, kwargs={"poll_interval": 0.3}, daemon=True, name="FNauto-web-remote"
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        srv, self._srv = (self._srv, None)
        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
        LATEST.clear()
