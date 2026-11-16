from __future__ import annotations

import threading

from version import UPDATE_REPO


class UpdateService:
    def __init__(self, settings, on_state=None, log=None, updater_factory=None, on_available=None):
        self.settings = settings
        self.on_state = on_state or (lambda _kind, _info=None: None)
        self.log = log or (lambda _message: None)
        self.on_available = on_available or (lambda _info: None)
        self._factory = updater_factory
        self._thread = None
        self.available = None

    def _updater(self):
        if self._factory is not None:
            return self._factory()
        from updater import AutoUpdater

        return AutoUpdater(repo=UPDATE_REPO)

    def check(self) -> bool:
        if not UPDATE_REPO.strip() or (self._thread is not None and self._thread.is_alive()):
            return False
        self.on_state("checking")
        self._thread = threading.Thread(target=self._check_work, daemon=True, name="FNauto-update-check")
        self._thread.start()
        return True

    def _check_work(self) -> None:
        try:
            updater = self._updater()
            if not getattr(updater, "frozen", True):
                self.on_state("dev")
                return
            info = updater.check_for_updates()
            self.available = info
            if info is None:
                self.on_state("latest")
                return
            self.on_state("available", info)
            self.on_available(info)
        except Exception as error:
            self.log(f"update: {type(error).__name__}")
            self.on_state("failed")
