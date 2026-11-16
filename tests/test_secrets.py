from __future__ import annotations

from pathlib import Path

from scripts.check_secrets import scan


def test_repository_has_no_committed_secrets():
    root = Path(__file__).resolve().parents[1]
    assert scan(root) == []
