import os
import queue
import threading
import time
from typing import Callable, List, Optional
import cv2
import numpy as np
import config

FOLDER_NAME = "loot_vault"
MAX_FILES = 100


def default_folder() -> str:
    return os.path.join(config.base_dir(), FOLDER_NAME)


class LootVault:
    def __init__(
        self,
        folder: Optional[str] = None,
        max_files: int = MAX_FILES,
        now: Callable[[], float] = time.time,
        sync: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.folder = folder or default_folder()
        self.max_files = max(1, int(max_files))
        self._now = now
        self._sync = sync
        self.log = log or (lambda _m: None)
        self._q = queue.Queue(maxsize=6)
        self._thread = None
        self._seq = 0

    def save(self, frame: np.ndarray, loop: int = 0) -> None:
        try:
            self._seq += 1
            item = (np.array(frame, copy=True), int(loop), self._now(), self._seq, "loot")
            if self._sync:
                self._write(*item)
                return
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="FNauto-loot")
                self._thread.start()
            self._q.put_nowait(item)
        except Exception:
            return None

    def save_treasure(self, frame: np.ndarray, loop: int = 0) -> None:
        try:
            self._seq += 1
            item = (np.array(frame, copy=True), int(loop), self._now(), self._seq, "treasure")
            if self._sync:
                self._write(*item)
                return
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="FNauto-loot")
                self._thread.start()
            self._q.put_nowait(item)
        except Exception:
            return None

    def _run(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=30)
            except queue.Empty:
                return None
            try:
                if len(item) == 5:
                    self._write(item[0], item[1], item[2], item[3], item[4])
                else:
                    self._write(item[0], item[1], item[2], item[3], "loot")
            except Exception:
                pass

    def _write(self, frame: np.ndarray, loop: int, t: float, seq: int, prefix: str = "loot") -> Optional[str]:
        os.makedirs(self.folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(t))
        path = os.path.join(self.folder, f"{prefix}_{stamp}_loop{loop}.png")
        if os.path.exists(path):
            path = os.path.join(self.folder, f"{prefix}_{stamp}_loop{loop}_{seq}.png")
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            return
        else:
            buf.tofile(path)
            self._trim()
            return path

    def files(self) -> List[str]:
        try:
            names = [n for n in os.listdir(self.folder) if n.startswith("loot_") and n.endswith(".png")]
        except OSError:
            return []
        return sorted(names)

    def _trim(self) -> None:
        names = self.files()
        for n in names[: max(0, len(names) - self.max_files)]:
            try:
                os.remove(os.path.join(self.folder, n))
            except OSError:
                pass

    def flush(self, timeout: float = 3.0) -> None:
        end = time.monotonic() + timeout
        while not self._q.empty() and time.monotonic() < end:
            time.sleep(0.02)

    def open_folder(self) -> bool:
        try:
            os.makedirs(self.folder, exist_ok=True)
            os.startfile(self.folder)
        except Exception:
            return False
        return True
