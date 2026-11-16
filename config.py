import json
import os
import random
import shutil
import sys
from dataclasses import dataclass, fields

APP_NAME = "FNauto"
SUPPORT_INVITE = "https://discord.gg/9cYDAtzuTF"
SETTINGS_FILE = "fnauto_settings.json"
LEGACY_SETTINGS_FILE = "pk-auto_settings.json"
TEMPLATE_NAMES = {
    "play": "play_btn.png",
    "continue": "continue_btn.png",
    "skip": "skip_btn.png",
    "return_lobby": "return_lobby_btn.png",
    "claim": "claim_btn.png",
    "claim_single": "claim_single_btn.png",
    "popup": "popup_btn.png",
    "hud": "hud_btn.png",
    "menu_btn": "menu_btn.png",
    "menu_return": "menu_return_btn.png",
    "storefront_play": "storefront_play_btn.png",
    "item_found": "item_found_btn.png",
}
MODES = {
    "A": "A: 通常ループ (続行→スキップ→ロビーへ)",
    "B": "B: 待機島で待ってEscから退出",
    "C": "C: 待機島で待って退出、アイテム発見でAへ切替",
}
OPTIONAL_TEMPLATES = {"popup", "item_found", "storefront_play", "claim_single", "claim"}
LANGS = {
    "ja": "日本語",
    "en": "English",
    "es": "Español (beta)",
    "pt": "Português (beta)",
    "ru": "Русский (beta)",
    "fr": "Français (beta)",
}
UI_THEMES = ("blue", "violet", "emerald", "amber", "light")
PLATE_LANGS = ("es", "pt", "ru", "fr")
LANG_INDEPENDENT = {"item_found", "storefront_play", "hud", "menu_return", "continue", "skip", "menu_btn"}
PLATES = {
    "play": {"roi": (0.0, 0.7, 0.4, 1.0), "threshold": 0.92},
    "return_lobby": {"roi": (0.55, 0.3, 1.0, 0.52), "threshold": 0.8},
    "claim": {"roi": (0.503, 0.8, 1.0, 1.0), "threshold": 0.93},
    "hud": {"roi": (0.0, 0.8, 0.3, 1.0), "threshold": 0.85},
    "menu_btn": {"roi": (0.7, 0.0, 1.0, 0.18), "threshold": 0.85},
    "menu_return": {"roi": (0.55, 0.0, 1.0, 0.36), "threshold": 0.85},
    "storefront_play": {"roi": (0.0, 0.55, 0.3, 0.8), "threshold": 0.8},
    "item_found": {"roi": (0.3, 0.0, 0.7, 0.4), "threshold": 0.75},
}
PLATE_UNUSED = {"claim_single"}


def plate_filename(key: str) -> str:
    return TEMPLATE_NAMES[key].replace(".png", "_plate.png")


def uses_template(key: str, lang: str) -> bool:
    return not (lang in PLATE_LANGS and key in PLATE_UNUSED)


def template_filename(key: str, lang: str = "ja") -> str:
    name = TEMPLATE_NAMES[key]
    if key in LANG_INDEPENDENT:
        return name
    else:
        if lang in PLATE_LANGS and key in PLATES:
            return plate_filename(key)
        else:
            if lang == "ja" or lang in PLATE_LANGS:
                return name
            else:
                return name.replace(".png", f"_{lang}.png")


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def assets_dir() -> str:
    return os.path.join(base_dir(), "assets")


def bundled_assets_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", base_dir()), "assets_default")
    else:
        return assets_dir()


def external_template_path(key: str, lang: str = "ja") -> str:
    return os.path.join(assets_dir(), template_filename(key, lang))


def template_path(key: str, lang: str = "ja") -> str:
    ext = external_template_path(key, lang)
    if os.path.isfile(ext):
        return ext
    else:
        bundled = os.path.join(bundled_assets_dir(), template_filename(key, lang))
        if os.path.isfile(bundled):
            return bundled
        else:
            return ext


@dataclass
class Settings:
    threshold: float = 0.82
    lang: str = "en"
    mode: str = "A"
    wait_b: float = 90.0
    wait_c: float = 90.0
    poll_interval: float = 2.0
    scales: tuple = tuple((round(0.6 + 0.1 * i, 2) for i in range(9)))
    jitter_px: int = 5
    delay_min: float = 0.15
    delay_max: float = 0.45
    click_cooldown: float = 3.0
    monitor_index: int = 1
    afk_enabled: bool = True
    afk_interval: float = 10.0
    afk_hold: float = 3.0
    afk_keys: tuple = ("w", "a", "s", "d")
    discord_webhook_url: str = ""
    telemetry_enabled: bool = True
    reward_shot_enabled: bool = False
    alert_enabled: bool = True
    report_hours: float = 0.0
    auto_stop_laps: int = 0
    space_enabled: bool = False
    space_seconds: float = 10.0
    space_count: int = 3
    auto_update_check: bool = False
    auto_relaunch_enabled: bool = True
    auto_relaunch_freeze_enabled: bool = True
    background_mode: bool = True
    background_ghost: bool = True
    ghost_show: bool = False
    background_post_keys: bool = False
    auto_mute_enabled: bool = False
    loot_vault_enabled: bool = True
    humanizer_enabled: bool = True
    coffee_break_enabled: bool = False
    auto_calibrate: bool = True
    stuck_timeout_min: float = 15.0
    squad_check_enabled: bool = False
    rescue_listening: bool = False
    afk_mouse_look: bool = True
    jitter_enabled: bool = True
    wait_jitter_percent: float = 0.15
    pickaxe_afk_enabled: bool = True
    pickaxe_slot_key: str = "1"
    bus_drop_enabled: bool = True
    mode_fix_enabled: bool = True
    bus_dive_seconds: float = 8.0
    bus_drop_min: int = 15
    bus_drop_max: int = 25
    pickaxe_min_s: float = 10.0
    pickaxe_max_s: float = 30.0
    ui_theme: str = "blue"
    ui_opacity: float = 1.0
    hud_x: int = -1
    hud_y: int = -1
    phone_remote_autostart: bool = False
    web_remote_enabled: bool = False
    web_remote_port: int = 8765
    web_remote_tunnel: bool = False
    topmost: bool = False
    window_x: int = -1
    window_y: int = -1

    @property
    def path(self):
        return user_settings_path()


USER_SETTING_KEYS = tuple(field.name for field in fields(Settings))
NUMBER_RANGES = {
    "auto_stop_laps": (0, 999),
    "report_hours": (0.0, 24.0),
    "ui_opacity": (0.4, 1.0),
    "wait_b": (10.0, 600.0),
    "wait_c": (10.0, 600.0),
    "threshold": (0.3, 0.99),
    "afk_interval": (1.0, 600.0),
    "afk_hold": (0.5, 30.0),
    "space_seconds": (1.0, 3600.0),
    "space_count": (1, 20),
    "stuck_timeout_min": (0.0, 240.0),
    "wait_jitter_percent": (0.0, 0.5),
    "pickaxe_min_s": (1.0, 3600.0),
    "pickaxe_max_s": (1.0, 3600.0),
    "bus_dive_seconds": (1.0, 60.0),
    "bus_drop_min": (1, 60),
    "bus_drop_max": (1, 60),
}
PICKAXE_SLOT_KEYS = tuple("1234567890")


def jitter_range(base_seconds: float, s: "Settings | None" = None) -> tuple:
    base = float(base_seconds)
    if s is None:
        s = Settings()
    if not getattr(s, "jitter_enabled", True) or base <= 0:
        return (base, base)
    else:
        pct = max(0.0, min(0.5, float(getattr(s, "wait_jitter_percent", 0.15))))
        return (base * (1.0 - pct), base * (1.0 + pct))


def get_jittered_wait(base_seconds: float, s: "Settings | None" = None, rng=random) -> float:
    lo, hi = jitter_range(base_seconds, s)
    if hi <= lo:
        return lo
    else:
        return rng.uniform(lo, hi)


def user_settings_path() -> str:
    override = os.environ.get("FNAUTO_SETTINGS")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    appdata = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, APP_NAME, SETTINGS_FILE)


def migrate_legacy_settings(legacy_path: str = "", target_path: str = "") -> bool:
    if not target_path and os.environ.get("FNAUTO_SETTINGS"):
        return False
    target = target_path or user_settings_path()
    legacy = legacy_path or os.path.join(base_dir(), LEGACY_SETTINGS_FILE)
    if os.path.exists(target) or not os.path.isfile(legacy):
        return False
    try:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        shutil.copy2(legacy, target)
        return True
    except OSError:
        return False


def load_user_settings(s: "Settings", path: str = "") -> None:
    try:
        with open(path or user_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        for k in USER_SETTING_KEYS:
            if k not in data:
                continue
            v, want = (data[k], type(getattr(s, k)))
            if want is float and isinstance(v, int) and (not isinstance(v, bool)):
                v = float(v)
            if want is tuple and isinstance(v, list):
                v = tuple(v)
            if not isinstance(v, want):
                continue
            if k in NUMBER_RANGES and (not NUMBER_RANGES[k][0] <= v <= NUMBER_RANGES[k][1]):
                continue
            if k == "pickaxe_slot_key" and v not in PICKAXE_SLOT_KEYS:
                continue
            if k == "lang" and v not in LANGS:
                continue
            if k == "mode" and v not in MODES:
                continue
            if k == "ui_theme" and v not in UI_THEMES:
                continue
            setattr(s, k, v)
    except Exception:
        return


def save_user_settings(s: "Settings", path: str = "") -> bool:
    target = path or user_settings_path()
    try:
        data = {k: getattr(s, k) for k in USER_SETTING_KEYS}
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
