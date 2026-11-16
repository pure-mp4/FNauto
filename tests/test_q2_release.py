from __future__ import annotations

import re
from pathlib import Path

import pytest

import config
import i18n
import version

from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_one_version_constant_and_release_metadata():
    assert version.APP_VERSION == "1.0.1"
    assert not hasattr(version, "__version__")
    info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    assert "FileVersion', '1.0.1.0'" in info
    assert "ProductVersion', '1.0.1.0'" in info
    assert "FileDescription', 'FNauto'" in info
    assert "OriginalFilename', 'FNauto.exe'" in info
    assert "LegalCopyright', 'Copyright (c) 2026 FNauto contributors'" in info
    assert "CompanyName" not in info


def test_version_is_used_by_build_ui_docs_and_issue_template():
    expected = (
        ("qt_app.py", "from version import APP_VERSION"),
        ("updater.py", "from version import APP_VERSION"),
        ("app_support.py", "from version import APP_VERSION"),
        ("scripts/package_release.bat", "from version import APP_VERSION"),
        ("README.md", "Version:** 1.0.1"),
        (".github/ISSUE_TEMPLATE/bug_report.md", "v1.0.1"),
    )
    old_patch = ".".join(("2", "2", "8"))
    old_legacy = ".".join(("2", "2", "9"))
    for relative, marker in expected:
        assert marker in (ROOT / relative).read_text(encoding="utf-8"), relative
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".bat", ".md", ".txt"}:
            continue
        if any(part in {".git", "build", "dist"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert old_patch not in text, path
        assert old_legacy not in text, path


def test_support_invite_is_public_and_in_every_language():
    assert config.SUPPORT_INVITE == "https://discord.gg/9cYDAtzuTF"
    for lang in config.LANGS:
        assert i18n.t(lang, "support_join")
        assert config.SUPPORT_INVITE.rsplit("/", 1)[-1] in i18n.t(lang, "support_server")
        assert any("discord.gg/9cYDAtzuTF" in text for _kind, text in i18n.guide(lang))


def test_readme_local_links_exist():
    documents = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            assert path.exists(), f"{document.name}: {target}"


def test_support_buttons_open_the_exact_invite_without_network(qapp, monkeypatch):
    pytest.importorskip("PySide6")
    Q = pytest.importorskip("qt_app")
    calls = []
    monkeypatch.setattr(Q.QDesktopServices, "openUrl", lambda url: calls.append(url.toString()) or True)
    settings = Q.Settings()
    discord = Q.DiscordPage(Q.Theme(), settings, Q.Signals(), None)
    guide = Q.GuidePage(Q.Theme())
    discord.support_button.clicked.emit()
    guide.support_button.clicked.emit()
    assert calls == [config.SUPPORT_INVITE, config.SUPPORT_INVITE]
    discord.deleteLater()
    guide.deleteLater()


def test_default_support_opener_uses_qdesktopservices(qapp, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    import qt_app

    seen = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: seen.append(url.toString()) or True)
    assert qt_app.open_support_invite(config.SUPPORT_INVITE) is True
    assert seen == [config.SUPPORT_INVITE]
