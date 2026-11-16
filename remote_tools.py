import time

import config
import i18n
import web_remote

WAIT_STATES = ("IN_MATCH", "B:WAITING", "B:LOADING")
KEYS = ("esc", "enter", "w", "a", "s", "d", "pickaxe")


class RemoteBridge:
    def __init__(self, settings, controller=None, log=None, start=None, stop=None, on_mode=None, on_power=None):
        self.settings, self.controller = settings, controller
        self._log, self._start, self._stop = log or (lambda _m: None), start, stop
        self._on_mode = on_mode
        self._on_power = on_power

    def labels(self) -> dict:
        return {"lang": i18n.norm(str(self.settings.get("lang", "en")))}

    def _running(self) -> bool:
        if self.controller is not None:
            try:
                return bool(self.controller.running())
            except Exception:
                return False
        return False

    def status(self) -> dict:
        st = {}
        if self.controller is not None:
            try:
                st = dict(self.controller.status)
            except Exception:
                st = {}
        running = self._running()
        t0 = st.get("t0")
        state = str(st.get("state", "IDLE"))
        eta = None
        if running and st.get("eta") is not None:
            base = float(st.get("eta"))
            eta_t = st.get("eta_t")
            eta = (
                max(0, int(round(base - (time.monotonic() - float(eta_t))))) if eta_t is not None else int(round(base))
            )
        return {
            "running": running,
            "state": state,
            "mode": str(self.settings.get("mode", "A")),
            "loops": int(st.get("loops", 0) or 0),
            "claims": int(st.get("claims", 0) or 0),
            "elapsed": int(time.time() - float(t0)) if running and t0 is not None else 0,
            "stuck": bool(st.get("stuck", self.settings.get("rescue_listening", False))) and running,
            "waiting": state in WAIT_STATES,
            "eta": eta,
            "tune": st.get("tune") if running else None,
            "relaunch": getattr(getattr(getattr(self.controller, "worker", None), "relauncher", None), "phase", "idle"),
            "alert": st.get("alert"),
            "log": [],
        }

    def frame_jpeg(self):
        try:
            return web_remote.LATEST.jpeg()
        except Exception:
            return None

    def _worker(self):
        return getattr(self.controller, "worker", None)

    def action(self, name: str, value: str = "") -> dict:
        name = str(name or "")
        if name == "mode":
            if value not in config.MODES:
                return {"ok": False, "error": "bad_mode"}
            if self._on_mode:
                self._on_mode(value)
            else:
                self.settings.set("mode", value)
            return {"ok": True}
        if name == "arm":
            return {"ok": True}
        if name in ("sleep", "kill", "relaunch"):
            if self._on_power is None:
                return {"ok": False, "error": "unsupported"}
            try:
                ok = self._on_power(name)
                return {"ok": bool(ok)}
            except Exception:
                return {"ok": False, "error": "failed"}
        running = self._running()
        if name == "start":
            if running:
                return {"ok": False, "error": "already_running"}
            if self._start:
                self._start()
            elif self.controller is not None:
                self.controller.start()
            return {"ok": True}
        if name == "stop":
            if not running:
                return {"ok": False, "error": "not_running"}
            if self._stop:
                self._stop()
            elif self.controller is not None:
                self.controller.stop()
            return {"ok": True}
        if name == "toggle":
            return self.action("stop" if running else "start")
        if name == "key":
            if value not in KEYS:
                return {"ok": False, "error": "bad_key"}
        if name in ("click", "space", "mute", "tap", "key"):
            if not running:
                return {"ok": False, "error": "not_running"}
            worker = self._worker()
            commands = getattr(worker, "commands", None)
            if commands is None:
                return {"ok": False, "error": "not_running"}
            try:
                if name == "tap":
                    rx, ry = (float(v) for v in str(value).split(","))
                    if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0):
                        raise ValueError
                    commands.put(("tap", rx, ry))
                else:
                    commands.put(("key", value) if name == "key" else name)
            except Exception:
                return {"ok": False, "error": "bad_request"}
            return {"ok": True}
        return {"ok": False, "error": "unknown_action"}


class RemoteService:
    def __init__(self, settings, bridge: RemoteBridge, host: str = "0.0.0.0", log=None):
        self.settings, self.bridge = settings, bridge
        self.log = log or (lambda _m: None)
        self.web = web_remote.WebRemote(bridge, int(settings.get("web_remote_port", 8765)), host=host)

    @property
    def running(self) -> bool:
        return self.web.running

    @property
    def token(self) -> str:
        return self.web.token

    @property
    def port(self) -> int:
        return self.web.port

    def set_public(self, allowed: bool) -> None:
        self.web.allow_public = bool(allowed)

    def url(self, ip: str = "") -> str:
        addr = ip or ("127.0.0.1" if str(self.web.host).startswith("127.") else "")
        return self.web.url(addr)

    def start(self) -> bool:
        if self.web.running:
            return True
        ok = self.web.start()
        if ok:
            self.settings.set("web_remote_enabled", True)
            self.log(i18n.t(str(self.settings.get("lang", "en")), "log_remote_on", url=self.url()))
        else:
            self.settings.set("web_remote_enabled", False)
            self.log(i18n.t(str(self.settings.get("lang", "en")), "rm_failed"))
        return ok

    def stop(self, quiet: bool = False) -> None:
        self.set_public(False)
        self.web.stop()
        self.settings.set("web_remote_enabled", False)
        if not quiet:
            self.log(i18n.t(str(self.settings.get("lang", "en")), "log_remote_off"))
