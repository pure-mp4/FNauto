import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from typing import Callable, Optional, Tuple
import updater

REPO = "cloudflare/cloudflared"
ASSET = "cloudflared-windows-amd64.exe"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
MAX_BYTES = 209715200
MIN_BYTES = 5242880
START_TIMEOUT_S = 45.0
CREATE_NO_WINDOW = 134217728
URL_RE = re.compile("https://([a-z0-9]+(?:-[a-z0-9]+)+)\\.trycloudflare\\.com", re.I)


class TunnelError(Exception):
    pass


def bin_dir(env=None) -> str:
    base = env or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FNauto", "bin")


def find_cloudflared(
    which: Callable[[str], Optional[str]] = shutil.which, env=None, isfile=os.path.isfile
) -> Optional[str]:
    found = which("cloudflared")
    if found:
        return found
    mine = os.path.join(bin_dir(env), "cloudflared.exe")
    return mine if isfile(mine) else None


def extract_url(line: str) -> Optional[str]:
    m = URL_RE.search(line or "")
    return f"https://{m.group(1).lower()}.trycloudflare.com" if m else None


def pick_asset(release) -> Tuple[str, int, str]:
    for a in (release.get("assets") if isinstance(release, dict) else None) or []:
        if not isinstance(a, dict) or a.get("name") != ASSET:
            continue
        url = str(a.get("browser_download_url") or "")
        if not url.startswith(DOWNLOAD_PREFIX):
            raise TunnelError("untrusted_url")
        digest = str(a.get("digest") or "")
        if not re.fullmatch("sha256:[0-9a-fA-F]{64}", digest):
            raise TunnelError("no_checksum")
        size = int(a.get("size") or 0)
        if size and (not MIN_BYTES <= size <= MAX_BYTES):
            raise TunnelError("verify")
        return (url, size, digest.split(":", 1)[1].lower())
    raise TunnelError("no_asset")


def download_cloudflared(
    dest_dir: Optional[str] = None, opener=None, progress: Callable[[int], None] = lambda _p: None
) -> str:
    opener = opener or updater.build_opener()
    dest_dir = dest_dir or bin_dir()
    target, tmp = (os.path.join(dest_dir, "cloudflared.exe"), os.path.join(dest_dir, "cloudflared.exe.part"))
    try:
        os.makedirs(dest_dir, exist_ok=True)
        req = urllib.request.Request(
            API_URL, headers={"User-Agent": "FNauto-tunnel", "Accept": "application/vnd.github+json"}
        )
        with opener.open(req, timeout=30) as r:
            url, size, sha = pick_asset(json.loads(r.read(2000000).decode("utf-8")))
        h, got, last = (hashlib.sha256(), 0, -1)
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "FNauto-tunnel"}), timeout=30) as r:
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_BYTES:
                        raise TunnelError("verify")
                    f.write(chunk)
                    h.update(chunk)
                    if size and int(got * 100 / size) != last:
                        last = int(got * 100 / size)
                        progress(min(99, last))
        with open(tmp, "rb") as f:
            head = f.read(2)
        if (size and got != size) or h.hexdigest() != sha or head != b"MZ" or got < MIN_BYTES:
            raise TunnelError("verify")
        os.replace(tmp, target)
        progress(100)
        return target
    except OSError:
        return
    except TunnelError:
        raise
    except (PermissionError, FileNotFoundError, NotADirectoryError) as e:
        raise TunnelError("not_writable") from e
    except Exception as e:
        raise TunnelError("network") from e
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _job_object():
    try:
        import ctypes
        from ctypes import wintypes

        k = ctypes.windll.kernel32
        k.CreateJobObjectW.restype = wintypes.HANDLE
        job = k.CreateJobObjectW(None, None)
        if not job:
            return None

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

        class EXT(ctypes.Structure):
            _fields_ = [
                ("Basic", BASIC),
                ("Io", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = EXT()
        info.Basic.LimitFlags = 8192
        if not k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        return job
    except Exception:
        return None


def _assign_to_job(job, proc) -> None:
    try:
        import ctypes

        ctypes.windll.kernel32.AssignProcessToJobObject(job, int(proc._handle))
    except Exception:
        return None


class Tunnel:
    def __init__(
        self,
        on_status: Callable[[str, str], None] = lambda s, d: None,
        popen=subprocess.Popen,
        finder=find_cloudflared,
        downloader=download_cloudflared,
        make_job=_job_object,
        timeout_s: float = START_TIMEOUT_S,
    ):
        self.on_status, self._popen, self._finder, self._downloader, self._make_job = (
            on_status,
            popen,
            finder,
            downloader,
            make_job,
        )
        self.timeout_s = timeout_s
        self.url = None
        self._proc = None
        self._job = None
        self._gen = 0
        self._lock = threading.Lock()
        atexit.register(self.stop)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _say(self, gen: int, status: str, detail: str = "") -> None:
        if gen == self._gen:
            try:
                self.on_status(status, detail)
            except Exception:
                return None

    def start(self, port: int, allow_download: bool = True) -> None:
        with self._lock:
            self._gen += 1
            gen = self._gen
        self._kill()
        self.url = None
        threading.Thread(
            target=self._run, args=(gen, int(port), allow_download), daemon=True, name="FNauto-tunnel"
        ).start()

    def _run(self, gen: int, port: int, allow_download: bool) -> None:
        try:
            exe = self._finder()
            if not exe:
                if not allow_download:
                    self._say(gen, "failed", "missing")
                    return
                self._say(gen, "downloading")
                exe = self._downloader()
            if gen != self._gen:
                return
            self._say(gen, "starting")
            proc = self._popen(
                [exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self._lock:
                if gen != self._gen:
                    self._terminate(proc)
                    return
                self._proc = proc
                self._job = self._make_job()
                if self._job:
                    _assign_to_job(self._job, proc)
            deadline = time.monotonic() + self.timeout_s
            threading.Thread(
                target=self._watchdog, args=(gen, proc, deadline), daemon=True, name="FNauto-tunnel-watch"
            ).start()
            for line in proc.stderr:
                url = extract_url(line)
                if not url:
                    continue
                if not (gen == self._gen):
                    continue
                if self.url is not None:
                    continue
                self.url = url
                self._say(gen, "ready", url)
            if gen == self._gen and proc.poll() is not None:
                self.url = None
                self._say(gen, "failed", "exited")
                return
        except TunnelError as e:
            self._say(gen, "failed", str(e.args[0]) if e.args else "error")
            return
        except Exception as e:
            self._say(gen, "failed", type(e).__name__)
            return

    def _watchdog(self, gen: int, proc, deadline: float) -> None:
        while time.monotonic() < deadline:
            if gen != self._gen or proc.poll() is not None or self.url:
                return
            time.sleep(0.25)
        if gen == self._gen and (not self.url):
            self._say(gen, "failed", "timeout")
            with self._lock:
                self._gen += 1
            self._kill()

    @staticmethod
    def _terminate(proc) -> None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
        except Exception:
            return None

    def _kill(self) -> None:
        with self._lock:
            proc, self._proc = (self._proc, None)
            job, self._job = (self._job, None)
        if proc is not None:
            self._terminate(proc)
        if job:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(job)
            except Exception:
                return None

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
            gen = self._gen
        self._kill()
        had = self.url is not None
        self.url = None
        if had:
            self._say(gen, "stopped")
