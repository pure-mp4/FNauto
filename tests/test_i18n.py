from __future__ import annotations

import i18n
import config


def test_all_languages_have_the_core_labels():
    for lang in config.LANGS:
        for key in ("start", "stop", "nav_home", "dm_help"):
            assert i18n.t(lang, key)


def test_guide_blocks_are_aligned():
    expected = len(i18n.guide("en"))
    for lang in config.LANGS:
        assert len(i18n.guide(lang)) == expected


def test_unknown_language_falls_back_to_english():
    assert i18n.norm("unknown") == "en"
    assert i18n.t("unknown", "start") == i18n.t("en", "start")


def test_removed_feature_labels_are_not_shipped():
    for lang in config.LANGS:
        text = str(i18n.UI[lang])
        assert "ex_biomotion" not in text
        assert "ex_macro_line" not in text
