import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional
from version import APP_VERSION, UPDATE_REPO

API_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 30.0
CHUNK = 65536
MIN_EXE_BYTES = 1000000
MAX_DOWNLOAD_BYTES = 419430400
MAX_NOTES_CHARS = 4000
STAGED_SUFFIX = ".new"
BACKUP_SUFFIX = ".bak"
DOWNLOAD_NAME = "FNauto_update.download"
RUNNER_NAME = "_update_runner.bat"
TRUSTED_HOST_SUFFIXES = ("github.com", "githubusercontent.com")
CREATE_NO_WINDOW = 134217728
CREATE_NEW_PROCESS_GROUP = 512
RUNNER_BAT = '@echo off\nsetlocal EnableExtensions\nset /a TRIES=0\ncopy /y "%FN_OLD%" "%FN_BAK%" >nul 2>&1\n:wait\nping -n 2 127.0.0.1 >nul\ndel /f /q "%FN_OLD%" >nul 2>&1\nif not exist "%FN_OLD%" goto swap\nset /a TRIES+=1\nif %TRIES% lss 90 goto wait\ngoto giveup\n:swap\nmove /y "%FN_NEW%" "%FN_OLD%" >nul 2>&1\nif errorlevel 1 goto restore\ndel /f /q "%FN_BAK%" >nul 2>&1\ngoto launch\n:restore\ncopy /y "%FN_BAK%" "%FN_OLD%" >nul 2>&1\n:giveup\ndel /f /q "%FN_NEW%" >nul 2>&1\ndel /f /q "%FN_BAK%" >nul 2>&1\n:launch\nstart "" "%FN_OLD%"\ndel "%~f0"\n'


class UpdateError(Exception):
    pass


_VER_RE = re.compile("^\\s*[vV]?(\\d+)(?:\\.(\\d+))?(?:\\.(\\d+))?(.*)$")
_PRE_RE = re.compile("^[-._]?(alpha|beta|rc|pre|dev)(?![a-z])", re.I)


def parse_version(text) -> Optional[tuple]:
    m = _VER_RE.match(str(text or ""))
    if not m:
        return
    else:
        nums = tuple((int(x) if x else 0 for x in m.group(1, 2, 3)))
        suffix = m.group(4).strip()
        pre = _PRE_RE.match(suffix)
        return nums + ((0, suffix.lower()) if pre else (1, ""))


def is_newer(latest, current) -> bool:
    a, b = (parse_version(latest), parse_version(current))
    return a is not None and b is not None and (a > b)


def _trusted_host(host: str) -> bool:
    host = (host or "").lower()
    return any((host == s or host.endswith("." + s) for s in TRUSTED_HOST_SUFFIXES))


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    pass

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or not _trusted_host(u.hostname):
            raise urllib.error.URLError(f"redirect to an untrusted address refused: {u.hostname}")
        else:
            return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener():
    return urllib.request.build_opener(_SafeRedirect)


def clean_env(env) -> dict:
    out = {k: v for k, v in env.items() if not k.upper().startswith("_PYI") and k.upper() != "_MEIPASS2"}
    out["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return out


@dataclass
class UpdateInfo:
    tag: str
    latest_version: str
    release_notes: str
    download_url: str
    asset_name: str
    size: int = 0
    sha256: str = ""
    page_url: str = ""


class AutoUpdater:
    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo: str = UPDATE_REPO,
        opener=None,
        frozen: Optional[bool] = None,
        exe_path: Optional[str] = None,
        url_ok: Optional[Callable[[str], bool]] = None,
        min_exe_bytes: int = MIN_EXE_BYTES,
    ):
        self.current = current_version
        self.repo = repo
        self._opener = opener or build_opener()
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.exe_path = exe_path or sys.executable
        self._url_ok = url_ok or self._repo_download_url
        self.min_exe_bytes = min_exe_bytes
        self.last_error = ""

    @property
    def can_self_replace(self) -> bool:
        return self.frozen

    @property
    def api_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/releases/latest"

    def _repo_download_url(self, url: str) -> bool:
        return isinstance(url, str) and url.startswith(f"https://github.com/{self.repo}/releases/download/")

    def _request(self, url: str, accept: str = "*/*"):
        return urllib.request.Request(url, headers={"User-Agent": f"FNauto-updater/{self.current}", "Accept": accept})

    def _pick_asset(self, assets) -> Optional[dict]:
        found = []
        for a in assets if isinstance(assets, list) else []:
            if not isinstance(a, dict):
                continue
            else:
                name, url = (str(a.get("name", "")), a.get("browser_download_url"))
                low = name.lower()
                if not (low.endswith(".exe") or low.endswith(".zip")) or not self._url_ok(url):
                    continue
                else:
                    found.append((0 if low.endswith(".exe") else 1, 0 if low.startswith("FNauto") else 1, name, a))
        return min(found, key=lambda t: t[:3])[3] if found else None

    def check_for_updates(self) -> Optional[UpdateInfo]:
        self.last_error = ""
        if not self.repo.strip():
            self.last_error = "disabled"
            return None
        try:
            with self._opener.open(
                self._request(self.api_url, "application/vnd.github+json"), timeout=API_TIMEOUT_S
            ) as r:
                rel = json.loads(r.read(2000000).decode("utf-8"))
            if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease"):
                return
            tag = str(rel.get("tag_name", ""))
            if not is_newer(tag, self.current):
                return
            asset = self._pick_asset(rel.get("assets"))
            if asset is None:
                self.last_error = "no_asset"
                return
            digest = str(asset.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            size = asset.get("size")
            return UpdateInfo(
                tag=tag,
                latest_version=tag.lstrip("vV"),
                release_notes=str(rel.get("body") or "")[:MAX_NOTES_CHARS],
                download_url=asset["browser_download_url"],
                asset_name=str(asset.get("name", "")),
                size=size if isinstance(size, int) and size > 0 else 0,
                sha256=sha if re.fullmatch("[0-9a-f]{64}", sha) else "",
                page_url=str(rel.get("html_url") or ""),
            )
        except Exception as e:
            self.last_error = type(e).__name__

    def check_async(self, callback: Callable[[Optional[UpdateInfo]], None]) -> threading.Thread:
        def work():
            info = self.check_for_updates()
            try:
                callback(info)
            except Exception:
                return None

        t = threading.Thread(target=work, daemon=True, name="FNauto-update-check")
        t.start()
        return t

    def _check_exe(self, path: str) -> None:
        with open(path, "rb") as f:
            head = f.read(2)
        if os.path.getsize(path) < self.min_exe_bytes or head != b"MZ":
            raise UpdateError("verify")

    def _extract_exe(self, zip_path: str, dest: str) -> None:
        with zipfile.ZipFile(zip_path) as z:
            members = [
                i
                for i in z.infolist()
                if not i.is_dir() and i.filename.lower().endswith(".exe") and (i.file_size <= MAX_DOWNLOAD_BYTES)
            ]
            if not members:
                raise UpdateError("verify")
            m = min(
                members,
                key=lambda i: (0 if os.path.basename(i.filename).lower().startswith("FNauto") else 1, i.filename),
            )
            with z.open(m) as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)

    def _download(self, url: str, path: str, progress: Callable[[int], None], size: int, sha256: str) -> None:
        h, got, last = (hashlib.sha256(), 0, (-1))
        with self._opener.open(self._request(url), timeout=READ_TIMEOUT_S) as r:
            try:
                total = int(r.headers.get("Content-Length") or 0)
            except (TypeError, ValueError, AttributeError):
                total = 0
            total = total or size
            if total > MAX_DOWNLOAD_BYTES:
                raise UpdateError("verify")
            with open(path, "wb") as f:
                while True:
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("verify")
                    f.write(chunk)
                    h.update(chunk)
                    if total:
                        pct = min(99, int(got * 100 / total))
                        if pct != last:
                            last = pct
                            progress(pct)
        if size and got != size or (sha256 and h.hexdigest().lower() != sha256.lower()):
            raise UpdateError("verify")

    def download_update(
        self, source, progress_callback: Optional[Callable[[int], None]] = None, sha256: str = "", size: int = 0
    ) -> str:
        url = source.download_url if isinstance(source, UpdateInfo) else str(source)
        if isinstance(source, UpdateInfo):
            sha256, size = (sha256 or source.sha256, size or source.size)
        if not self.frozen:
            raise UpdateError("not_frozen")
        else:
            if not self._url_ok(url):
                raise UpdateError("untrusted_url")
            else:
                progress = progress_callback or (lambda _p: None)
                exe_dir = os.path.dirname(os.path.abspath(self.exe_path))
                tmp = os.path.join(exe_dir, DOWNLOAD_NAME)
                staged = os.path.abspath(self.exe_path) + STAGED_SUFFIX
                try:
                    progress(0)
                    self._download(url, tmp, progress, size, sha256)
                    with open(tmp, "rb") as f:
                        is_zip = f.read(2) == b"PK"
                    if is_zip:
                        self._extract_exe(tmp, staged)
                    else:
                        os.replace(tmp, staged)
                    self._check_exe(staged)
                    progress(100)
                    return staged
                except UpdateError:
                    self._discard(staged)
                    raise
                except (PermissionError, FileNotFoundError, NotADirectoryError) as e:
                    self._discard(staged)
                    raise UpdateError("not_writable") from e
                except (OSError, zipfile.BadZipFile, urllib.error.URLError) as e:
                    self._discard(staged)
                    raise UpdateError("network" if isinstance(e, urllib.error.URLError) else "verify") from e
                finally:
                    self._discard(tmp)

    @staticmethod
    def _discard(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            return None

    def launch_runner(self, staged_path: str) -> str:
        if not self.frozen:
            raise UpdateError("not_frozen")
        else:
            exe = os.path.abspath(self.exe_path)
            exe_dir = os.path.dirname(exe)
            bat = os.path.join(exe_dir, RUNNER_NAME)
            try:
                with open(bat, "w", encoding="ascii", newline="\r\n") as f:
                    f.write(RUNNER_BAT)
            except OSError as e:
                raise UpdateError("not_writable") from e
            env = clean_env(os.environ)
            env.update(FN_OLD=exe, FN_NEW=os.path.abspath(staged_path), FN_BAK=exe + BACKUP_SUFFIX)
            flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            subprocess.Popen(
                [bat],
                env=env,
                cwd=exe_dir,
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return bat

    def download_and_apply_update(
        self,
        download_url,
        progress_callback: Optional[Callable[[int], None]] = None,
        sha256: str = "",
        size: int = 0,
        exit_fn: Optional[Callable[([], None)]] = None,
    ) -> None:
        staged = self.download_update(download_url, progress_callback, sha256, size)
        self.launch_runner(staged)
        (exit_fn or (lambda: sys.exit(0)))()
