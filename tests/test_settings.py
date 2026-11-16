from __future__ import annotations

import json
import os

import pytest

import config


def test_default_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("FNAUTO_SETTINGS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.user_settings_path() == str(tmp_path / "FNauto" / "fnauto_settings.json")


def test_override_wins(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere" / "settings.json"
    monkeypatch.setenv("FNAUTO_SETTINGS", str(target))
    assert config.user_settings_path() == str(target)


def test_legacy_settings_copy_is_one_time(tmp_path):
    legacy = tmp_path / "legacy.json"
    target = tmp_path / "FNauto" / "fnauto_settings.json"
    legacy.write_text('{"lang": "ja"}', encoding="utf-8")
    assert config.migrate_legacy_settings(str(legacy), str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == {"lang": "ja"}
    assert not config.migrate_legacy_settings(str(legacy), str(target))
    target.write_text('{"lang": "en"}', encoding="utf-8")
    assert not config.migrate_legacy_settings(str(legacy), str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == {"lang": "en"}


def test_migration_never_overwrites_new_settings(tmp_path):
    legacy = tmp_path / "legacy.json"
    target = tmp_path / "fnauto_settings.json"
    legacy.write_text('{"lang": "ja"}', encoding="utf-8")
    target.write_text('{"lang": "fr"}', encoding="utf-8")
    assert not config.migrate_legacy_settings(str(legacy), str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == {"lang": "fr"}


def test_environment_override_blocks_implicit_migration(monkeypatch, tmp_path):
    monkeypatch.setenv("FNAUTO_SETTINGS", str(tmp_path / "custom.json"))
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}", encoding="utf-8")
    assert not config.migrate_legacy_settings(str(legacy))


def test_round_trip_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    settings = config.Settings()
    settings.lang = "fr"
    settings.mode = "B"
    settings.report_hours = 3.0
    assert config.save_user_settings(settings, str(path))

    loaded = config.Settings()
    config.load_user_settings(loaded, str(path))
    assert (loaded.lang, loaded.mode, loaded.report_hours) == ("fr", "B", 3.0)

    path.write_text(
        json.dumps(
            {
                "lang": "xx",
                "mode": "Z",
                "threshold": "wrong",
                "report_hours": 100,
                "pickaxe_slot_key": "x",
                "unknown_key": 1,
            }
        ),
        encoding="utf-8",
    )
    guarded = config.Settings()
    config.load_user_settings(guarded, str(path))
    assert guarded.lang == "en"
    assert guarded.mode == "A"
    assert guarded.threshold == config.Settings().threshold
    assert guarded.report_hours == config.Settings().report_hours


def test_unknown_and_removed_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "macro_v2_enabled": True,
                "acoustic_trigger_enabled": True,
                "lang": "ja",
            }
        ),
        encoding="utf-8",
    )
    settings = config.Settings()
    config.load_user_settings(settings, str(path))
    assert settings.lang == "ja"
    with pytest.raises(AttributeError):
        _ = settings.macro_v2_enabled


def test_save_creates_appdata_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("FNAUTO_SETTINGS", raising=False)
    config.save_user_settings(config.Settings())
    assert os.path.isfile(tmp_path / "FNauto" / "fnauto_settings.json")
