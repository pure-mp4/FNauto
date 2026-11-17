from types import SimpleNamespace

import controller


class SlowExitWorker:
    def __init__(self):
        self.calls = 0

    def is_alive(self):
        self.calls += 1
        return self.calls < 3

    def join(self, _timeout=None):
        return None


def test_stop_watcher_waits_for_worker_exit():
    idle = []
    ctrl = controller.MacroController(
        SimpleNamespace(mode="A", lang="en", telemetry_enabled=False),
        on_idle=lambda: idle.append(True),
    )
    worker = SlowExitWorker()

    ctrl._watch_worker(worker)

    assert worker.calls >= 3
    assert idle == [True]
