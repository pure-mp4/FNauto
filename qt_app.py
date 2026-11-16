from __future__ import annotations

import os
import sys
import json
import time
import ctypes
import threading
import tempfile
import html
from collections import deque

from PySide6.QtCore import (
    Qt,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QUrl,
    QTimer,
    Signal,
    QEasingCurve,
    QPropertyAnimation,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextLayout,
    QTextOption,
    QKeySequence,
    QShortcut,
    QGuiApplication,
)
from PySide6.QtSvg import QSvgRenderer
import icons
import app_icon
import i18n
import config
from version import APP_VERSION
import app_support
from update_tools import UpdateService
from version import UPDATE_REPO
from i18n import UI
from redact import redact
from i18n_ui import UI_SHELL

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QScrollArea,
    QPlainTextEdit,
    QTextBrowser,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QStyledItemDelegate,
    QSpinBox,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFrame,
)

from hud_qt import MiniHud
from remote_qt import RemoteWindow
from remote_tools import RemoteBridge, RemoteService
from snip_qt import SnipOverlay

TR = None


def open_support_invite(url: str = config.SUPPORT_INVITE) -> bool:
    return bool(QDesktopServices.openUrl(QUrl(url)))


EN = UI["en"]
EN_UI = UI_SHELL["en"]
EXTRA = {
    "diag_title": {
        "en": "Diagnostics",
        "fr": "Diagnostic",
        "es": "Diagnóstico",
        "pt": "Diagnóstico",
        "ru": "Диагностика",
        "ja": "診断",
    },
    "loop_title": {
        "en": "Loop mode",
        "fr": "Mode de boucle",
        "es": "Modo de bucle",
        "pt": "Modo de ciclo",
        "ru": "Режим цикла",
        "ja": "ループモード",
    },
    "hint": {
        "en": "F8: stop  ·  Ctrl+Tab: switch tabs",
        "fr": "F8 : arrêter  ·  Ctrl+Tab : changer d’onglet",
        "es": "F8: detener  ·  Ctrl+Tab: cambiar de pestaña",
        "pt": "F8: parar  ·  Ctrl+Tab: trocar de aba",
        "ru": "F8: стоп  ·  Ctrl+Tab: переключение вкладок",
        "ja": "F8: 停止  ·  Ctrl+Tab: タブ切替",
    },
    "notif_title": {
        "en": "Notification Center",
        "fr": "Centre de notifications",
        "es": "Centro de notificaciones",
        "pt": "Central de notificações",
        "ru": "Центр уведомлений",
        "ja": "通知センター",
    },
    "stopping": {
        "en": "Stopping…",
        "fr": "Arrêt en cours…",
        "es": "Deteniendo…",
        "pt": "Parando…",
        "ru": "Остановка…",
        "ja": "停止中…",
    },
    "dm_card_title": {
        "en": "Discord notifications",
        "fr": "Notifications Discord",
        "es": "Notificaciones de Discord",
        "pt": "Notificações do Discord",
        "ru": "Уведомления Discord",
        "ja": "Discord通知",
    },
    "first_run": {
        "en": "Settings file not found - defaults are loaded. See Guide for setup.",
        "fr": "Fichier de réglages introuvable - valeurs par défaut chargées. Voir le guide.",
        "es": "No se encontró el archivo de ajustes: se cargan los valores predeterminados. Consulta la guía.",
        "pt": "Arquivo de configurações não encontrado: padrões carregados. Veja o guia.",
        "ru": "Файл настроек не найден — загружены значения по умолчанию. См. справку.",
        "ja": "設定ファイルが見つからないため、初期値で起動しました。説明を確認してください。",
    },
    "yes": {"en": "Yes", "fr": "Oui", "es": "Sí", "pt": "Sim", "ru": "Да", "ja": "はい"},
    "no": {"en": "No", "fr": "Non", "es": "No", "pt": "Não", "ru": "Нет", "ja": "いいえ"},
    "admin_button": {
        "en": "Restart as administrator",
        "fr": "Redémarrer en administrateur",
        "es": "Reiniciar como administrador",
        "pt": "Reiniciar como administrador",
        "ru": "Перезапустить от администратора",
        "ja": "管理者として再起動",
    },
    "admin_failed": {
        "en": "Could not request administrator rights",
        "fr": "Impossible de demander les droits administrateur",
        "es": "No se pudieron solicitar permisos de administrador",
        "pt": "Não foi possível pedir permissões de administrador",
        "ru": "Не удалось запросить права администратора",
        "ja": "管理者権限を要求できませんでした",
    },
}
for _lang in UI:
    for _k, _v in EXTRA.items():
        UI[_lang].setdefault(_k, _v.get(_lang, _v["en"]))


class Translator:
    def __init__(self, settings):
        self.settings = settings
        self.lang = i18n.norm(str(settings.get("lang", "en")))
        self.items = []

    def t(self, key, **kw):
        return i18n.t(self.lang, key, **kw)

    def add(self, widget, key, setter=None, fmt=None):
        fn = setter or (lambda w, s: w.setText(s))
        self.items.append((widget, key, fn, fmt))
        fn(widget, self.t(key, **(fmt or {})))
        return widget

    def retranslate(self):
        for w, key, setter, fmt in self.items:
            setter(w, self.t(key, **(fmt or {})))

    def set_lang(self, code):
        code = i18n.norm(code)
        self.lang = code
        self.settings.set("lang", code)
        self.retranslate()


APP_NAME = "FNauto"
WIN_W, WIN_H = 816, 860
RADIUS = 16
TB = 56
RAIL_W = 58
GAP = 16
PAD = 14
R_CARD = 14
REDUCE_MOTION = False
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

THEMES = {
    "blue": dict(
        BG0="#08111F",
        GLASS="#18243A",
        FIELD="#111B2E",
        FIELD_HI="#16233A",
        TILE="#1E2D43",
        EDGE="#2A3A58",
        LINE="#22304A",
        TEXT="#ECF1F8",
        MUTED="#7C8FA8",
        ACCENT="#2F6FED",
        ACCENT_HI="#4E8BFF",
        ON="#2ED47A",
        OFF="#3A4660",
        DANGER="#FF5C6C",
        DANGER_HI="#FF7B88",
        INSET="#0B1424",
        SEL="#1E3A6B",
        HOVER="#1D2B45",
        GOOD="#2ED47A",
        SIDE_TOP="#0D1A2D",
        SIDE_BOT="#0A1424",
        EDGE_SOFT="#2A3A58",
        TRACK="#14233A",
    ),
    "violet": dict(
        BG0="#0A0C1C",
        GLASS="#111528",
        FIELD="#171B33",
        FIELD_HI="#1E2340",
        TILE="#12162B",
        EDGE="#2A2C52",
        LINE="#1E2140",
        TEXT="#EDEBFF",
        MUTED="#A6A2CE",
        ACCENT="#8B5CF6",
        ACCENT_HI="#A78BFA",
        ON="#34D399",
        OFF="#2B2B4C",
        DANGER="#FF5C6C",
        DANGER_HI="#FF7B88",
        INSET="#080A18",
        SEL="#1C2040",
        HOVER="#191D38",
        GOOD="#6EE7B7",
        SIDE_TOP="#0D1024",
        SIDE_BOT="#0A0C1C",
        EDGE_SOFT="#3D3A6E",
        TRACK="#1E2340",
    ),
    "emerald": dict(
        BG0="#05120E",
        GLASS="#0A1A16",
        FIELD="#10261F",
        FIELD_HI="#16332A",
        TILE="#0C1F1B",
        EDGE="#1E3A33",
        LINE="#16302A",
        TEXT="#E6F7F0",
        MUTED="#8FB3A8",
        ACCENT="#2ED47A",
        ACCENT_HI="#5BE39A",
        ON="#2ED47A",
        OFF="#1C3A31",
        DANGER="#FF5C6C",
        DANGER_HI="#FF7B88",
        INSET="#04100C",
        SEL="#123A2E",
        HOVER="#103028",
        GOOD="#4ADE80",
        SIDE_TOP="#071915",
        SIDE_BOT="#05120E",
        EDGE_SOFT="#2E5C4E",
        TRACK="#123029",
    ),
    "amber": dict(
        BG0="#120E07",
        GLASS="#1A1409",
        FIELD="#241B0C",
        FIELD_HI="#2E2310",
        TILE="#1E1709",
        EDGE="#3B2E15",
        LINE="#2B2110",
        TEXT="#FBF3E2",
        MUTED="#BFA98A",
        ACCENT="#F5A524",
        ACCENT_HI="#FFC15E",
        ON="#2ED47A",
        OFF="#3B2E15",
        DANGER="#FF5C6C",
        DANGER_HI="#FF7B88",
        INSET="#0D0A05",
        SEL="#33280F",
        HOVER="#291F0C",
        GOOD="#4ADE80",
        SIDE_TOP="#171207",
        SIDE_BOT="#120E07",
        EDGE_SOFT="#5C4820",
        TRACK="#2B2110",
    ),
    "light": dict(
        BG0="#E9EFF7",
        GLASS="#FFFFFF",
        FIELD="#EEF3FA",
        FIELD_HI="#E3EAF5",
        TILE="#F4F7FB",
        EDGE="#D2DDEB",
        LINE="#E2E9F3",
        TEXT="#0B1B2E",
        MUTED="#5C6E88",
        ACCENT="#2F6FED",
        ACCENT_HI="#4E8BFF",
        ON="#22A55B",
        OFF="#C9D5E6",
        DANGER="#DC2837",
        DANGER_HI="#EF4444",
        INSET="#F7FAFD",
        SEL="#E1EAF7",
        HOVER="#EFF4FB",
        GOOD="#22A55B",
        SIDE_TOP="#EDF2F9",
        SIDE_BOT="#E4EBF5",
        EDGE_SOFT="#B9C7DE",
        TRACK="#DCE5F0",
    ),
}
THEME_ORDER = ("blue", "violet", "emerald", "amber", "light")


class Theme(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.name = "blue"
        self.tokens = dict(THEMES["blue"])

    def c(self, key: str, alpha: int | None = None) -> QColor:
        col = QColor(self.tokens[key])
        if alpha is not None:
            col.setAlpha(alpha)
        return col

    def set(self, name: str) -> None:
        if name not in THEMES:
            return
        self.name = name
        self.tokens = dict(THEMES[name])
        self.changed.emit(name)

    def qss(self) -> str:
        t = self.tokens
        return f"""
QWidget {{ color: {t["TEXT"]}; font-family: Inter, 'Segoe UI'; font-size: 10pt; }}
QLabel {{ background: transparent; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: {t["FIELD"]}; color: {t["TEXT"]}; border: 1px solid {t["EDGE"]};
  border-radius: 8px; padding: 3px 8px; min-height: 24px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {t["ACCENT"]}; background: {t["FIELD_HI"]}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0px; subcontrol-origin: border; background: transparent; border: none; }}
QComboBox::drop-down {{ border: none; width: 0px; }}
QComboBox[chevron="true"] {{ padding-right: 32px; }}
QComboBox QAbstractItemView {{ border-radius: 10px; padding: 4px; outline: 0; }}
QComboBox QAbstractItemView::item {{ height: 32px; padding-left: 8px; color: {t["TEXT"]}; }}
QComboBox QAbstractItemView::item:selected {{ background: {t["ACCENT"]}; color: #FFFFFF; border-radius: 8px; }}
QComboBox QAbstractItemView {{ background: {t["FIELD"]}; color: {t["TEXT"]}; border: 1px solid {t["EDGE"]}; }}
QPushButton {{ background: {t["FIELD"]}; color: {t["TEXT"]}; border: 1px solid {t["EDGE"]};
  border-radius: 8px; padding: 7px 14px; min-height: 22px; }}
QPushButton:hover {{ background: {t["HOVER"]}; }}
QLabel[role="muted"] {{ color: {t["MUTED"]}; }}
"""


def settings_path() -> str:
    config.migrate_legacy_settings()
    return config.user_settings_path()


class Settings(QObject):
    changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.path = settings_path()
        self.existed = os.path.exists(self.path)
        self.first_run = not self.existed
        self.values = {
            "ui_theme": "blue",
            "ui_opacity": 1.0,
            "topmost": False,
            "lang": "en",
            "mode": "A",
            "wait_b": 90.0,
            "wait_c": 90.0,
            "auto_stop_laps": 0,
            "threshold": 0.82,
            "background_mode": True,
            "background_ghost": True,
            "ghost_show": False,
            "afk_enabled": True,
            "afk_interval": 10.0,
            "afk_hold": 3.0,
            "space_enabled": False,
            "space_seconds": 10.0,
            "space_count": 3,
            "discord_webhook_url": "",
            "telemetry_enabled": True,
            "alert_enabled": True,
            "report_hours": 0.0,
            "auto_mute_enabled": False,
            "afk_mouse_look": True,
            "humanizer_enabled": True,
            "jitter_enabled": True,
            "wait_jitter_percent": 0.15,
            "loot_vault_enabled": True,
            "mode_fix_enabled": True,
            "bus_drop_enabled": True,
            "bus_dive_seconds": 8.0,
            "pickaxe_afk_enabled": True,
            "pickaxe_min_s": 10.0,
            "pickaxe_max_s": 30.0,
            "coffee_break_enabled": False,
            "reward_shot_enabled": False,
            "auto_calibrate": True,
            "squad_check_enabled": False,
            "stuck_timeout_min": 15.0,
            "auto_relaunch_enabled": True,
            "auto_relaunch_freeze_enabled": True,
            "hud_x": -1,
            "hud_y": -1,
            "phone_remote_autostart": False,
            "web_remote_enabled": False,
            "web_remote_port": 8765,
            "web_remote_tunnel": False,
            "poll_interval": 2.0,
            "scales": tuple(round(0.6 + 0.1 * i, 2) for i in range(9)),
            "jitter_px": 5,
            "delay_min": 0.15,
            "delay_max": 0.45,
            "click_cooldown": 3.0,
            "monitor_index": 1,
            "afk_keys": ("w", "a", "s", "d"),
            "auto_update_check": False,
            "background_post_keys": False,
            "rescue_listening": False,
            "pickaxe_slot_key": "1",
            "bus_drop_min": 15,
            "bus_drop_max": 25,
            "window_x": -1,
            "window_y": -1,
        }
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.values.update({k: v for k, v in data.items() if k in self.values})
        except Exception:
            pass

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        if self.values.get(key) == value:
            return
        self.values[key] = value
        self.changed.emit(key, value)
        self.save()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.values, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class Signals(QObject):
    opacity = Signal(int)
    start_requested = Signal()
    state_changed = Signal(str, float, int)
    log_line = Signal(str)
    error = Signal(str)
    language_changed = Signal(str)
    worker_idle = Signal()
    hotkey_stop = Signal()
    tool_result = Signal(str, str, str, str)
    status = Signal(dict)
    notify = Signal(str, str)
    running = Signal(bool)
    discord_status = Signal(str)
    webhook_changed = Signal()
    hud_status = Signal(dict)
    hud_requested = Signal()
    remote_requested = Signal()
    crop_requested = Signal(str)
    tunnel_status = Signal(str, str)
    tunnel_requested = Signal(bool)
    web_remote_requested = Signal(bool)


def load_fonts() -> None:
    for f in ("Outfit-Regular.ttf", "Outfit-Bold.ttf", "Inter-Regular.ttf", "Inter-Bold.ttf"):
        p = os.path.join(FONT_DIR, f)
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    for p in (r"C:\Windows\Fonts\YuGothR.ttc", r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)


def family(bold: bool = False) -> str:
    return "Outfit" if bold else "Inter"


def rounded_path(rect: QRectF, r: float) -> QPainterPath:
    p = QPainterPath()
    p.addRoundedRect(rect, r, r)
    return p


def icon_pixmap(kind: str, size: int, color: str) -> QPixmap:
    if kind in icons.BODY:
        return icons.pixmap(kind, size, color)
    paths = {
        "home": "M4 11 L12 4 L20 11 L20 20 L14 20 L14 14 L10 14 L10 20 L4 20 Z",
        "sliders": "M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M16 17h4",
        "chat": "M4 5h16v10H9l-5 4z",
        "spark": "M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z",
        "list": "M5 7h14M5 12h14M5 17h14",
        "wrench": "M14 4a4 4 0 015 5l-9 9-4 1 1-4z",
        "book": "M5 4h6v16H5zM13 4h6v16h-6z",
        "bell": "M12 3a5 5 0 015 5v4l2 3H5l2-3V9a5 5 0 015-5zM10 19h4",
        "exit": "M14 4h5v16h-5M4 12h11M11 8l4 4-4 4",
        "min": "M6 12h12",
        "close": "M7 7l10 10M17 7L7 17",
    }
    if kind == "bell":
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path d="{paths["bell"]}" fill="{color}" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/></svg>'
        )
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        r = QSvgRenderer(svg.encode())
        p = QPainter(pm)
        r.render(p)
        p.end()
        return pm
    path = {
        "home": "home",
        "play": "sliders",
        "discord": "chat",
        "extras": "spark",
        "log": "list",
        "tools": "wrench",
        "guide": "book",
        "bell": "bell",
        "min": "min",
        "close": "close",
        "exit": "exit",
    }.get(kind, "list")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path d="{paths[path]}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    r = QSvgRenderer(svg.encode())
    p = QPainter(pm)
    r.render(p)
    p.end()
    return pm


class Card(QWidget):
    def __init__(self, theme: Theme, tile: bool = False, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.tile = tile
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fill = self.theme.c("TILE" if self.tile else "GLASS")
        edge = self.theme.c("EDGE")
        p.setPen(QPen(edge, 1))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), R_CARD, R_CARD)
        p.end()


class Toggle(QWidget):
    toggled = Signal(bool)

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.on = False
        self.hover = 0.0
        self.slide = 0.0
        self.setFixedSize(44, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._step)

    def _step(self, v) -> None:
        self.slide = float(v)
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.set_on(not self.on, emit=True)

    def set_on(self, value: bool, emit: bool = False) -> None:
        self.on = bool(value)
        self.anim.stop()
        self.anim.setStartValue(self.slide)
        self.anim.setEndValue(1.0 if self.on else 0.0)
        self.anim.start()
        if emit:
            self.toggled.emit(self.on)

    def set_text(self, text: str) -> None:
        self.text = text
        self.setMinimumWidth(QFontMetrics(QFont(family(True), 10)).horizontalAdvance(text) + 32)
        self.update()

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        track = t.c("ACCENT") if self.on else t.c("OFF")
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 44, 22), 11, 11)
        knob = 18
        x = 2 + (44 - knob - 4) * self.slide
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 2, knob, knob))
        p.end()


class _SpinChrome:
    LEFT_PAD, ARROW_W, RIGHT_PAD = 12, 30, 8

    def _spin_init(self, theme=None) -> None:
        self._theme = theme
        self._hover = False
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMinimumHeight(30)
        self.lineEdit().setTextMargins(self.LEFT_PAD, 0, 0, 0)
        self.lineEdit().setStyleSheet("background: transparent; border: none;")
        self._fit_width()

    def _position_line_edit(self) -> None:
        le = self.lineEdit()
        le.setGeometry(0, 3, max(1, self.width() - self.ARROW_W), max(1, self.height() - 6))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_line_edit()

    def showEvent(self, e):
        super().showEvent(e)
        self._position_line_edit()

    def _fit_width(self) -> None:
        try:
            text = self.textFromValue(self.maximum())
            chars = len(str(text)) + 1
            fm = QFontMetrics(self.font())
            width = fm.horizontalAdvance("0" * chars) + self.LEFT_PAD + self.ARROW_W + self.RIGHT_PAD
            self.setFixedWidth(max(84, width))
        except Exception:
            self.setMinimumWidth(84)

    def setRange(self, *args):
        super().setRange(*args)
        self._fit_width()

    def setDecimals(self, decimals):
        super().setDecimals(decimals)
        self._fit_width()

    def setSuffix(self, suffix):
        super().setSuffix(suffix)
        self._fit_width()

    def setPrefix(self, prefix):
        super().setPrefix(prefix)
        self._fit_width()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().x() >= self.width() - self.ARROW_W:
            self.stepBy(1 if e.position().y() < self.height() / 2 else -1)
            e.accept()
            return
        super().mousePressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._theme
        col = t.c("TEXT") if t else self.palette().color(self.foregroundRole())
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("HOVER") if t else self.palette().highlight())
            p.drawRoundedRect(QRectF(self.width() - self.ARROW_W + 1, 2, self.ARROW_W - 3, self.height() - 4), 6, 6)
        p.setPen(QPen(col, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx = self.width() - self.ARROW_W / 2 - 1
        cy = self.height() / 2
        p.drawLine(QPointF(cx - 4.5, cy - 4), QPointF(cx, cy - 9))
        p.drawLine(QPointF(cx, cy - 9), QPointF(cx + 4.5, cy - 4))
        p.drawLine(QPointF(cx - 4.5, cy + 4), QPointF(cx, cy + 9))
        p.drawLine(QPointF(cx, cy + 9), QPointF(cx + 4.5, cy + 4))
        p.end()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.clearFocus()
            return
        super().keyPressEvent(e)


class FocusSpinBox(_SpinChrome, QSpinBox):
    def __init__(self, theme=None, parent=None):
        super().__init__(parent)
        self._spin_init(theme)


class FocusDoubleSpinBox(_SpinChrome, QDoubleSpinBox):
    def __init__(self, theme=None, parent=None):
        super().__init__(parent)
        self._spin_init(theme)


class RoundButton(QWidget):
    clicked = Signal()

    def __init__(self, text: str, theme: Theme, kind: str = "primary", parent=None):
        super().__init__(parent)
        self.text, self.theme, self.kind = text, theme, kind
        self.hover = 0.0
        self.press = 0.0
        self.setFixedHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        fm = QFontMetrics(QFont(family(True), 10))
        self.setMinimumWidth(fm.horizontalAdvance(text) + 32)

    def set_text(self, text: str) -> None:
        self.text = text
        self.setMinimumWidth(QFontMetrics(QFont(family(True), 10)).horizontalAdvance(text) + 32)
        self.update()

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.press = 0.0
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.press = 1.0
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        self.press = 0.0
        self.update()
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        if self.kind == "primary":
            base = t.c("ACCENT")
            if self.hover:
                base = t.c("ACCENT_HI")
        elif self.kind == "danger":
            base = t.c("DANGER")
        else:
            base = t.c("FIELD")
        p.setPen(QPen(t.c("EDGE") if self.kind == "ghost" else base, 1))
        p.setBrush(base)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        p.setPen(QColor("#FFFFFF") if self.kind in ("primary", "danger") else t.c("TEXT"))
        p.setFont(QFont(family(True), 10))
        p.drawText(self.rect(), Qt.AlignCenter, self.text)
        p.end()


class Slider(QWidget):
    valueChanged = Signal(int)
    HOVER_R = 11
    INSET = HOVER_R + 2
    HEIGHT = 2 * HOVER_R + 4

    def __init__(self, theme: Theme, lo: int = 40, hi: int = 100, val: int = 92, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.lo, self.hi, self.val = lo, hi, val
        self.hover = 0.0
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(160)

    def setValue(self, v: int) -> None:
        v = max(self.lo, min(self.hi, int(v)))
        if v != self.val:
            self.val = v
            self.update()
            self.valueChanged.emit(self.val)

    def _at(self, x: float) -> int:
        frac = max(0.0, min(1.0, (x - self.INSET) / max(1, self.width() - 2 * self.INSET)))
        return round(self.lo + frac * (self.hi - self.lo))

    def handle_rect(self) -> QRectF:
        frac = (self.val - self.lo) / max(1, self.hi - self.lo)
        cx = self.INSET + frac * (self.width() - 2 * self.INSET)
        return QRectF(cx - self.HOVER_R, self.height() / 2 - self.HOVER_R, self.HOVER_R * 2, self.HOVER_R * 2)

    def mousePressEvent(self, e) -> None:
        self.setValue(self._at(e.position().x()))
        self.valueChanged.emit(self.val)

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.LeftButton:
            self.setValue(self._at(e.position().x()))
            self.valueChanged.emit(self.val)

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        y = self.height() / 2
        x0 = self.INSET
        x1 = self.width() - self.INSET
        p.setPen(Qt.NoPen)
        p.setBrush(t.c("TRACK"))
        p.drawRoundedRect(QRectF(x0, y - 3, max(1, x1 - x0), 6), 3, 3)
        frac = (self.val - self.lo) / (self.hi - self.lo)
        cx = x0 + frac * (x1 - x0)
        p.setBrush(t.c("ACCENT"))
        p.drawRoundedRect(QRectF(x0, y - 3, max(1, cx - x0), 6), 3, 3)
        r = 9 + 2 * self.hover
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(t.c("ACCENT"), 2))
        p.drawEllipse(QPointF(cx, y), r, r)
        p.end()


class ThemeTile(QWidget):
    picked = Signal(str)

    def __init__(self, name: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.name, self.theme = name, theme
        self.hover = 0.0
        self.setFixedSize(66, 58)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.picked.emit(self.name)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = THEMES[self.name]
        selected = self.theme.name == self.name
        edge = QColor(pal["ACCENT"] if selected else pal["EDGE_SOFT"])
        if self.hover and not selected:
            edge = QColor(pal["ACCENT_HI"])
        rect = QRectF(3.5, 3.5, 59, 38)
        p.setPen(QPen(edge, 2 if selected else 1))
        p.setBrush(QColor(pal["GLASS"]))
        p.drawRoundedRect(rect, 9, 9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["SIDE_TOP"]))
        p.drawRoundedRect(QRectF(10, 10, 14, 26), 4, 4)
        p.setBrush(QColor(pal["ACCENT"]))
        p.drawEllipse(QPointF(16, 16), 3, 3)
        p.drawRoundedRect(QRectF(29, 25, 20, 4), 2, 2)
        p.setPen(QColor(self.theme.tokens["TEXT"] if selected else self.theme.tokens["MUTED"]))
        p.setFont(QFont(family(False), 7))
        p.drawText(QRectF(0, 41, 66, 16), Qt.AlignCenter, self.name.capitalize())
        p.end()


class StatusPill(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.running = False
        self.pulse = 0.0
        self.fm = QFontMetrics(QFont(family(True), 9))
        self._fit()

    def _fit(self) -> None:
        texts = (i18n.t(TR.lang, "st_stopped"), i18n.t(TR.lang, "st_running")) if TR else ("Stopped", "Running")
        w = max(self.fm.horizontalAdvance(t) for t in texts)
        self.setFixedSize(14 + 7 + 8 + w + 14, 28)
        if self.parent() and getattr(self.parent(), "pill", None) is not None:
            self.parent()._pill_moved()
        self.timer = QTimer(self)
        self.timer.setInterval(110)
        self.timer.timeout.connect(self._tick)

    def set_running(self, run: bool) -> None:
        self.running = bool(run)
        if run:
            self.timer.start()
        else:
            self.timer.stop()
            self.pulse = 0.0
        self.update()

    def _tick(self) -> None:
        self.pulse = (self.pulse + 0.08) % 1.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        label = (
            i18n.t(TR.lang, "st_running" if self.running else "st_stopped")
            if TR
            else ("Running" if self.running else "Stopped")
        )
        total = self.width()
        float(total)
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("INSET"))
        p.drawRoundedRect(QRectF(0.5, 0.5, total - 1, 27), 14, 14)
        color = t.c("GOOD") if self.running else QColor("#8B93A5")
        cy = 14
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(14 + 3.5, cy), 3.5, 3.5)
        p.setPen(t.c("TEXT"))
        p.setFont(QFont(family(True), 9))
        p.drawText(QRectF(14 + 7 + 8, 0, total - 29, 28), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.end()


class TitleBar(QWidget):
    bell = Signal()
    minimise = Signal()
    close = Signal()
    outside_clicked = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.buttons = ("close", "min", "bell")
        self.hover = None
        self.hover_t = 0.0
        self.unread = 0
        self.badge_pop = 1.0
        self.pill = StatusPill(theme, self)
        self.setFixedHeight(TB)
        self.setMouseTracking(True)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(120)
        self.anim.valueChanged.connect(self._step)

    def _pill_moved(self) -> None:
        self.pill.move((int(self.width()) - self.pill.width()) // 2, (TB - 28) // 2)

    def resizeEvent(self, _e) -> None:
        self._pill_moved()

    def _step(self, v) -> None:
        self.hover_t = float(v)
        self.update()

    def _button_rects(self):
        bw, bh, gap = 36, 32, 36
        bx = self.width() - 16 - bw / 2
        cy = TB / 2
        out = {}
        for key in self.buttons:
            out[key] = QRectF(bx - bw / 2, cy - bh / 2, bw, bh)
            bx -= gap
        return out

    def _hit(self, pos):
        for key, r in self._button_rects().items():
            if r.contains(QPointF(pos)):
                return key
        return None

    def mousePressEvent(self, e) -> None:
        key = self._hit(e.position())
        if key:
            if key != "bell":
                self.outside_clicked.emit()
            return
        if e.button() == Qt.LeftButton:
            self.outside_clicked.emit()
        if e.position().x() < self.width() - 180 and e.button() == Qt.LeftButton:
            win = self.window()
            if win.windowHandle():
                win.windowHandle().startSystemMove()

    def mouseReleaseEvent(self, e) -> None:
        key = self._hit(e.position())
        if key == "bell":
            self.bell.emit()
        elif key == "min":
            self.minimise.emit()
        elif key == "close":
            self.close.emit()

    def mouseMoveEvent(self, e) -> None:
        key = self._hit(e.position())
        if key != self.hover:
            self.hover = key
            self.anim.stop()
            self.anim.setStartValue(self.hover_t)
            self.anim.setEndValue(1.0 if key else 0.0)
            self.anim.start()
            self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        cy = self.height() / 2
        mark = 26
        p.drawPixmap(QRectF(22, cy - mark / 2, mark, mark).toRect(), app_icon.pixmap(mark))
        p.setPen(t.c("TEXT"))
        p.setFont(QFont(family(True), 11))
        p.drawText(QRectF(22 + mark + 10, 0, 200, TB), Qt.AlignLeft | Qt.AlignVCenter, APP_NAME)
        for key, r in self._button_rects().items():
            if key == self.hover or (key == self.hover and self.hover_t > 0):
                col = t.c("DANGER") if key == "close" else t.c("HOVER")
                col.setAlphaF(0.55 * self.hover_t)
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 8, 8)
            col = "#FFFFFF" if key == "close" and self.hover == "close" else t.tokens["MUTED"]
            pm = icon_pixmap(key, 20, col)
            p.drawPixmap(QPointF(r.center().x() - 10, r.center().y() - 10), pm)
            if key == "bell" and self.unread:
                rad = 8 * self.badge_pop
                center = QPointF(r.center().x() + 9, r.center().y() - 8)
                p.setPen(QPen(self.theme.c("BG0"), 1.5))
                p.setBrush(self.theme.c("ACCENT"))
                p.drawEllipse(center, rad, rad)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(QFont(family(True), 6))
                p.drawText(
                    QRectF(center.x() - rad, center.y() - rad, rad * 2, rad * 2),
                    Qt.AlignCenter,
                    str(min(99, self.unread)),
                )
        p.end()


ICON_NAMES = ("home", "play", "discord", "extras", "log", "tools", "guide")


class Rail(QWidget):
    clicked = Signal(str)
    hovered = Signal(str)
    quit_clicked = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.active = "home"
        self.hover = None
        self.fade = 1.0
        self.log_unread = 0
        self.setFixedWidth(RAIL_W)
        self.setMouseTracking(True)

    def quit_center(self) -> QPoint:
        return QPoint(RAIL_W // 2, self.height() - 14 - 14 - 22 - 21)

    def icon_center(self, name: str) -> QPoint:

        if name == "quit":
            return self.quit_center()
        i = ICON_NAMES.index(name)
        return QPoint(RAIL_W // 2, 22 + 48 * i + 24)

    def _at(self, pos):
        for name in ICON_NAMES:
            c = self.icon_center(name)
            if (pos - c).manhattanLength() < 26:
                return name
        if (pos - self.quit_center()).manhattanLength() < 26:
            return "quit"
        return None

    def mousePressEvent(self, e) -> None:
        name = self._at(e.position().toPoint())
        if name == "quit":
            self.quit_clicked.emit()
        elif name:
            self.clicked.emit(name)

    def mouseMoveEvent(self, e) -> None:
        name = self._at(e.position().toPoint())
        if name != self.hover:
            self.hover = name
            self.hovered.emit(name)
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = None
        self.hovered.emit("")
        self.update()

    def set_active(self, name: str) -> None:
        self.active = name
        self.update()

    def set_log_unread(self, count: int) -> None:
        self.log_unread = max(0, min(99, int(count)))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        p.setPen(Qt.NoPen)
        p.setBrush(t.c("SIDE_TOP"))
        p.drawRoundedRect(QRectF(0, 0, RAIL_W, self.height()), 14, 14)
        for i, name in enumerate(ICON_NAMES):
            c = self.icon_center(name)
            r = QRectF(c.x() - 19, c.y() - 19, 38, 38)
            active = name == self.active
            if active:
                p.setBrush(t.c("SEL"))
                p.setPen(QPen(t.c("ACCENT").darker(120), 1))
                p.drawRoundedRect(r, 9, 9)
                p.setPen(QPen(t.c("ACCENT"), 3))
                p.drawLine(QPointF(2, c.y() - 10), QPointF(2, c.y() + 10))
            elif name == self.hover:
                p.setBrush(t.c("HOVER"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r, 9, 9)
            col = "#6aa8ff" if active else ("#ffffff" if name == self.hover else "#8da2c0")
            pm = icon_pixmap(name, 26, col)
            p.drawPixmap(QPointF(c.x() - 13, c.y() - 13), pm)
            if name == "log" and self.log_unread:
                center = QPointF(c.x() + 12, c.y() - 12)
                p.setPen(QPen(t.c("BG0"), 1.5))
                p.setBrush(t.c("ACCENT"))
                p.drawEllipse(center, 7, 7)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(QFont(family(True), 6))
                p.drawText(
                    QRectF(center.x() - 7, center.y() - 7, 14, 14), Qt.AlignCenter, str(min(99, self.log_unread))
                )
        qc = self.quit_center()
        if self.hover == "quit":
            p.setBrush(t.c("HOVER"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(qc.x() - 21, qc.y() - 21, 42, 42), 9, 9)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(
            QPointF(qc.x() - 13, qc.y() - 13), icon_pixmap("exit", 26, "#ffffff" if self.hover == "quit" else "#8da2c0")
        )
        p.setPen(t.c("MUTED"))
        p.setFont(QFont(family(False), 7))
        p.drawText(QRectF(0, self.height() - 28, RAIL_W, 14), Qt.AlignCenter, f"v{APP_VERSION}")
        p.end()


class Tooltip(QWidget):
    def __init__(self, theme: Theme):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.theme = theme
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def show_for(self, text: str, global_pos: QPoint) -> None:
        self.label.setText(text)
        self.label.setStyleSheet(f"color:{self.theme.tokens['TEXT']}; background: transparent; font-size: 9pt;")
        fm = self.label.fontMetrics()
        self.setFixedSize(fm.horizontalAdvance(text) + 20, fm.height() + 10)
        self.label.setGeometry(10, 5, fm.horizontalAdvance(text), fm.height())
        self.move(global_pos)
        self.show()
        self.raise_()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.theme.c("EDGE_SOFT"), 1))
        p.setBrush(self.theme.c("HOVER"))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        p.end()


class _LangDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(32)
        return size


class ChevronCombo(QComboBox):
    def __init__(self, theme=None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setProperty("chevron", True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setItemDelegate(_LangDelegate(self))
        self.apply_theme()
        self.setMinimumWidth(150)
        self._fit_labels = []

    def apply_theme(self) -> None:
        if not self.theme:
            return
        t = self.theme.tokens
        self.setStyleSheet(
            f"QComboBox {{ background: {t['FIELD']}; color: {t['TEXT']}; "
            f"border: 1px solid {t['EDGE']}; border-radius: 8px; padding: 3px 8px; min-height: 24px; }}"
            f"QComboBox:focus {{ border: 1px solid {t['ACCENT']}; background: {t['FIELD_HI']}; }}"
            "QComboBox::drop-down { width: 0px; border: none; }"
            'QComboBox[chevron="true"] { padding-right: 32px; }'
        )
        self.view().setStyleSheet(
            f"QAbstractItemView {{ background: {t['FIELD']}; color: {t['TEXT']}; "
            f"border: 1px solid {t['EDGE']}; border-radius: 10px; padding: 4px; outline: 0; }}"
            f"QAbstractItemView::item {{ height: 32px; padding-left: 8px; color: {t['TEXT']}; }}"
            f"QAbstractItemView::item:selected {{ background: {t['ACCENT']}; color: #FFFFFF; border-radius: 8px; }}"
        )
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.clearFocus()
            return
        super().keyPressEvent(e)

    def fit(self, labels) -> None:
        self._fit_labels = [str(t) for t in labels]
        fm = QFontMetrics(self.font())
        self.setFixedWidth(max(fm.horizontalAdvance(str(t)) for t in labels) + 54)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self._fit_labels:
            self.fit(self._fit_labels)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = self.theme.c("MUTED") if self.theme else self.palette().color(self.foregroundRole())
        p.setPen(QPen(col, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx = self.width() - 17
        cy = self.height() / 2 - 3
        p.drawLine(QPointF(cx - 4.5, cy), QPointF(cx, cy + 4.5))
        p.drawLine(QPointF(cx, cy + 4.5), QPointF(cx + 4.5, cy))
        p.end()


class Radio(QWidget):
    picked = Signal(str)

    def __init__(self, key: str, text: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.key, self.text, self.theme = key, text, theme
        self.selected = False
        self.hover = 0.0
        self.setMinimumHeight(22)
        self.setCursor(Qt.PointingHandCursor)

    def set_text(self, text: str) -> None:
        self.text = text
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.picked.emit(self.key)

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        cy = self.height() / 2
        edge = t.c("ACCENT") if (self.selected or self.hover) else t.c("EDGE_SOFT")
        p.setPen(QPen(edge, 1.5))
        p.setBrush(t.c("GLASS"))
        p.drawEllipse(QPointF(9, cy), 7, 7)
        if self.selected:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("ACCENT"))
            p.drawEllipse(QPointF(9, cy), 3.5, 3.5)
        p.setPen(t.c("TEXT"))
        fr = QFont(family(False))
        fr.setPixelSize(13)
        p.setFont(fr)
        p.drawText(QRectF(24, 0, self.width() - 24, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        p.end()


class Page(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.cards = []
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(12)
        self.outer.addSpacing(0)
        self.cards_layout = self.outer

    def add_title(self, title_key: str, sub_key: str) -> None:
        box = QVBoxLayout()
        box.setSpacing(2)
        h = QLabel()
        h.setObjectName("PageHeading")
        h.setStyleSheet("font-size:22px; font-weight:600;")
        s = QLabel()
        s.setObjectName("PageSub")
        s.setProperty("role", "muted")
        s.setStyleSheet("font-size:13px;")
        if TR is not None:
            TR.add(h, title_key)
            TR.add(s, sub_key)
        else:
            h.setText(i18n.t("en", title_key))
            s.setText(i18n.t("en", sub_key))
        box.addWidget(h)
        box.addWidget(s)
        self.outer.addLayout(box)
        self.outer.addSpacing(8)

    def text_label(
        self, key: str, muted: bool = False, wrap: bool = False, bold: bool = False, size: int = 0
    ) -> QLabel:
        lab = QLabel()
        lab.setWordWrap(wrap)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if muted:
            lab.setProperty("role", "muted")
        style = ""
        if size:
            style += f"font-size:{size}px; "
        if bold:
            style += "font-weight:600; "
        if style:
            lab.setStyleSheet(style)
        if TR is not None:
            TR.add(lab, key)
        else:
            lab.setText(i18n.t("en", key))
        return lab

    def card_title(self, key: str) -> QLabel:
        return self.text_label(key, bold=True, size=15)

    def toggle_row(self, settings: Settings, key: str, label_key: str, after=None):
        row = QWidget()
        row.setObjectName("ToggleRow_" + key)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        toggle = Toggle(self.theme)
        toggle.set_on(bool(settings.get(key, False)))

        def changed(value: bool) -> None:
            settings.set(key, bool(value))
            if after is not None:
                after(bool(value))

        toggle.toggled.connect(changed)
        label = self.text_label(label_key, wrap=True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(toggle, 0, Qt.AlignTop)
        lay.addWidget(label, 1)
        row.setMinimumHeight(24)
        return row, toggle

    def spin_row(self, label_key: str, spin, unit_key: str, mid_key: str = "", second=None):
        row = QWidget()
        row.setObjectName("SpinRow_" + label_key)
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        label = self.text_label(label_key, muted=True, wrap=True)
        label.setFixedWidth(190)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        spin.setMinimumHeight(30)
        grid.addWidget(label, 0, 0)
        grid.addWidget(spin, 0, 1)
        if second is not None:
            mid = self.text_label(mid_key, muted=True, wrap=True)
            mid.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            second.setMinimumHeight(30)
            unit = self.text_label(unit_key, muted=True, wrap=True)
            unit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            grid.addWidget(mid, 0, 2)
            grid.addWidget(second, 0, 3)
            grid.addWidget(unit, 0, 4)
            grid.setColumnStretch(4, 1)
        else:
            unit = self.text_label(unit_key, muted=True, wrap=True)
            unit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            grid.addWidget(unit, 0, 2)
            grid.setColumnStretch(2, 1)
        grid.setColumnMinimumWidth(0, 190)
        return row

    def add_card(self, tile: bool = False) -> Card:
        c = Card(self.theme, tile)
        self.cards.append(c)
        return c


class HomePage(Page):
    def __init__(self, theme: Theme, settings: Settings, signals: Signals, parent=None):
        super().__init__(theme, parent)
        self.settings, self.signals = settings, signals
        self.last_state = "IDLE"
        self._stopping = False
        self.add_title("nav_home", "sub_home")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.values = {}
        self.caps = {}
        for key, cap_key, default in (
            ("state", "tile_state", "IDLE"),
            ("laps", "tile_laps", "0"),
            ("score", "tile_score", "0.00"),
        ):
            card = self.add_card(tile=True)
            card.setFixedHeight(84)
            label = QLabel()
            label.setStyleSheet(f"font-size:12px; font-weight:600; color:{theme.tokens['MUTED']};")
            val = QLabel(default)
            val.setStyleSheet(
                f"font-size:28px; font-weight:600; color:{theme.tokens['MUTED'] if key == 'state' else theme.tokens['TEXT']};"
            )
            card.body.addWidget(label)
            card.body.addWidget(val)
            self.values[key] = val
            self.caps[key] = label
            if TR is not None:
                TR.add(label, cap_key)
            row.addWidget(card, 3 if key == "state" else 2)
        self.outer.addLayout(row)
        self.start = RoundButton("Start", theme, "primary")
        self.relaunch = RoundButton("", theme, "ghost")
        self.start.clicked.connect(signals.start_requested.emit)
        brow = QHBoxLayout()
        brow.setSpacing(10)
        brow.addWidget(self.start)
        brow.addWidget(self.relaunch)
        brow.addStretch(1)
        self.outer.addLayout(brow)
        if TR is not None:
            TR.add(self.relaunch, "relaunch_button", lambda w, txt: w.set_text(txt))
            TR.add(self.start, "start", lambda w, txt: w.set_text(txt))
        else:
            self.relaunch.set_text("Relaunch Game")
        self.top = Toggle(theme)
        self.top.set_on(bool(settings.get("topmost")))
        self.top.toggled.connect(lambda v: settings.set("topmost", v))
        trow = QHBoxLayout()
        trow.addWidget(self.top)
        top_lab = QLabel()
        trow.addWidget(top_lab)
        trow.addStretch(1)
        if TR is not None:
            TR.add(top_lab, "topmost")
        self.outer.addLayout(trow)
        hint = QLabel()
        hint.setStyleSheet(f"color:{theme.tokens['MUTED']}")
        self.outer.addWidget(hint)
        if TR is not None:
            TR.add(hint, "hint")
        loop = self.add_card()
        title = QLabel()
        title.setStyleSheet(f"font-size:15px; font-weight:600; color:{theme.tokens['TEXT']};")
        loop.body.addWidget(title)
        if TR is not None:
            TR.add(title, "loop_title")
        self.radios = {}
        current = str(settings.get("mode", "A"))
        for key, text in (
            ("A", "A: Normal loop (Continue → Skip → Lobby)"),
            ("B", "B: Wait on the island, then leave via Esc"),
            ("C", "C: Island loop, switches to A when an item is found"),
        ):
            r = Radio(key, text, theme)
            r.selected = key == current
            r.picked.connect(lambda k: self._pick_mode(k))
            if TR is not None:
                TR.add(r, f"mode_{key}", lambda w, txt: w.set_text(txt))
            self.radios[key] = r
            loop.body.addWidget(r)
        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(0)
        fields.setColumnMinimumWidth(0, 190)
        fields.setColumnStretch(0, 0)
        fields.setColumnStretch(1, 0)
        fields.setColumnStretch(2, 0)
        fields.setColumnStretch(3, 1)
        self.spin_b = FocusSpinBox(theme)
        self.spin_b.setRange(10, 600)
        self.spin_b.setValue(int(settings.get("wait_b", 90) or 90))
        self.spin_b.valueChanged.connect(lambda v: settings.set("wait_b", v))
        self.spin_c = FocusSpinBox(theme)
        self.spin_c.setRange(10, 600)
        self.spin_c.setValue(int(settings.get("wait_c", 90) or 90))
        self.spin_c.valueChanged.connect(lambda v: settings.set("wait_c", v))
        self.spin_stop = FocusSpinBox(theme)
        self.spin_stop.setRange(0, 999)
        self.spin_stop.setValue(int(settings.get("auto_stop_laps", 0) or 0))
        self.spin_stop.valueChanged.connect(lambda v: settings.set("auto_stop_laps", v))
        rows = (
            ("b_pre", self.spin_b, "b_post"),
            ("c_pre", self.spin_c, "c_post"),
            ("auto_stop_pre", self.spin_stop, "auto_stop_post"),
        )
        for i, (pre, spin, post) in enumerate(rows):
            lp = QLabel()
            lp.setWordWrap(False)
            lp.setMinimumWidth(190)
            lu = QLabel()
            lu.setWordWrap(False)
            fields.addWidget(lp, i, 0)
            fields.addWidget(spin, i, 1)
            fields.addWidget(lu, i, 2)
            fields.setRowMinimumHeight(i, 44)
            if TR is not None:
                TR.add(lp, pre)
                TR.add(lu, post)
        loop.body.addLayout(fields)
        self.outer.addWidget(loop)
        lrow = QHBoxLayout()
        lrow.setSpacing(10)
        lang_lab = QLabel()
        lrow.addWidget(lang_lab)
        if TR is not None:
            TR.add(lang_lab, "lang_label")
        self.combo = ChevronCombo(theme)
        labels = list(config.LANGS.values())
        self.combo.addItems(labels)
        self.combo.fit(labels)
        lang = i18n.norm(str(settings.get("lang", "en")))
        codes = list(config.LANGS)
        self.combo.setCurrentIndex(codes.index(lang) if lang in codes else 1)
        self.combo.currentIndexChanged.connect(lambda i: self._pick_lang(codes[i]))
        lrow.addWidget(self.combo)
        lrow.addStretch(1)
        self.outer.addLayout(lrow)
        self.outer.addStretch(1)

    def _pick_lang(self, code: str) -> None:
        if TR is not None:
            TR.set_lang(code)
        self.signals.language_changed.emit(code)

    def _pick_mode(self, key: str) -> None:
        self.settings.set("mode", key)
        for k, r in self.radios.items():
            r.selected = k == key
            r.update()

    def _sync_running_text(self) -> None:
        run = bool(self.signals.running_state)
        if self._stopping:
            self.start.setEnabled(False)
            self.start.set_text(TR.t("stopping") if TR else "Stopping…")
            return
        self.start.setEnabled(True)
        self.start.set_text((TR.t("stop") if run else TR.t("start")) if TR else ("Stop" if run else "Start"))
        self.values["state"].setText(str(self.last_state) if run else "IDLE")
        self.values["state"].setStyleSheet(
            f"font-size:28px; font-weight:600; color:{self.theme.tokens['TEXT'] if run else self.theme.tokens['MUTED']};"
        )

    def set_running(self, run: bool) -> None:
        if run and not self.signals.running_state:
            self.last_state = "IDLE"
        self._stopping = False
        self.signals.running_state = run
        self._sync_running_text()

    def set_stopping(self) -> None:
        self._stopping = True
        self.start.setEnabled(False)
        self.start.set_text(TR.t("stopping") if TR else "Stopping…")

    def set_state(self, state: str, score: float, laps: int) -> None:
        self.last_state = str(state or "IDLE")
        label = self.last_state if self.signals.running_state else "IDLE"
        self.values["state"].setText(label)
        self.values["score"].setText(f"{score:.2f}")
        self.values["laps"].setText(str(laps))

    def retranslate_dynamic(self) -> None:
        if TR is not None:
            self._sync_running_text()


class PlayPage(Page):
    def __init__(self, theme: Theme, settings: Settings, signals: Signals, parent=None):
        super().__init__(theme, parent)
        self.settings, self.signals = settings, signals
        self.toggles = {}
        self.spins = {}
        self.cap_key = "play"
        self.add_title("nav_play", "sub_play")

        bg = self.add_card()
        bg.setObjectName("BackgroundCard")
        bg.body.addWidget(self.card_title("sec_background"))
        for key, text_key in (
            ("background_mode", "bg_check"),
            ("background_ghost", "ghost_check"),
            ("ghost_show", "ghost_show_check"),
        ):
            row, toggle = self.toggle_row(settings, key, text_key)
            self.toggles[key] = toggle
            bg.body.addWidget(row)
        self.outer.addWidget(bg)

        keys = self.add_card()
        keys.setObjectName("KeysCard")
        keys.body.addWidget(self.card_title("sec_keys"))
        row, toggle = self.toggle_row(settings, "afk_enabled", "afk_check")
        self.toggles["afk_enabled"] = toggle
        keys.body.addWidget(row)
        afk_int = self._double_spin(1, 600, 1, 0, self._number("afk_interval", 10.0))
        afk_int.setObjectName("AfkInterval")
        afk_int.valueChanged.connect(lambda v: self.settings.set("afk_interval", float(v)))
        self.spins["afk_interval"] = afk_int
        afk_hold = self._double_spin(0.5, 30, 0.5, 1, self._number("afk_hold", 3.0))
        afk_hold.setObjectName("AfkHold")
        afk_hold.valueChanged.connect(lambda v: self.settings.set("afk_hold", float(v)))
        self.spins["afk_hold"] = afk_hold
        keys.body.addWidget(self.spin_row("afk_pre", afk_int, "afk_post", "afk_mid", afk_hold))
        row, toggle = self.toggle_row(settings, "space_enabled", "space_check")
        self.toggles["space_enabled"] = toggle
        keys.body.addWidget(row)
        space_sec = self._double_spin(1, 600, 1, 0, self._number("space_seconds", 10.0))
        space_sec.setObjectName("SpaceSeconds")
        space_sec.valueChanged.connect(lambda v: self.settings.set("space_seconds", float(v)))
        self.spins["space_seconds"] = space_sec
        space_count = FocusSpinBox(theme)
        space_count.setRange(1, 50)
        space_count.setKeyboardTracking(False)
        space_count.setValue(self._integer("space_count", 3))
        space_count.setObjectName("SpaceCount")
        space_count.valueChanged.connect(lambda v: self.settings.set("space_count", int(v)))
        self.spins["space_count"] = space_count
        keys.body.addWidget(self.spin_row("space_pre", space_sec, "space_post", "space_mid", space_count))
        self.outer.addWidget(keys)

        card = self.add_card()
        card.setObjectName("MatchCard")
        card.body.addWidget(self.card_title("sec_match"))
        lab = self.text_label("threshold", muted=True)
        card.body.addWidget(lab)
        stored = float(settings.get("threshold", 0.82))
        val = max(50, min(95, int(round(stored * 100))))
        self.threshold_value = QLabel(f"{val / 100:.2f}")
        self.threshold_value.setProperty("role", "muted")
        self.threshold_value.setMinimumWidth(42)
        self.threshold_slider = Slider(theme, 50, 95, val)
        self.threshold_slider.setObjectName("ThresholdSlider")
        self.threshold_slider.valueChanged.connect(self._threshold)
        row = QHBoxLayout()
        row.addWidget(self.threshold_slider, 1)
        row.addWidget(self.threshold_value)
        card.body.addLayout(row)

        self.cap_combo = ChevronCombo(theme)
        self.cap_combo.setObjectName("TemplateCombo")
        template_keys = list(config.TEMPLATE_NAMES)
        self.cap_combo.addItems(template_keys)
        self.cap_combo.fit(template_keys)
        self.cap_combo.setCurrentIndex(template_keys.index("play") if "play" in template_keys else 0)
        self.cap_combo.currentTextChanged.connect(self._cap_changed)
        self.crop_button = RoundButton("", theme, "ghost")
        self.crop_button.setObjectName("CropButton")
        if TR is not None:
            TR.add(self.crop_button, "crop", lambda w, txt: w.set_text(txt))
        else:
            self.crop_button.set_text(i18n.t("en", "crop"))
        self.crop_button.clicked.connect(self._crop)
        crow = QHBoxLayout()
        crow.setSpacing(10)
        crow.addWidget(self.cap_combo)
        crow.addWidget(self.crop_button)
        crow.addStretch(1)
        card.body.addLayout(crow)
        self.outer.addWidget(card)
        self.outer.addStretch(1)

    def _double_spin(self, lo: float, hi: float, step: float, decimals: int, value: float) -> QDoubleSpinBox:
        spin = FocusDoubleSpinBox(self.theme)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        spin.setValue(float(value))
        return spin

    def _number(self, key: str, default: float) -> float:
        try:
            return float(self.settings.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _integer(self, key: str, default: int) -> int:
        try:
            return int(float(self.settings.get(key, default)))
        except (TypeError, ValueError):
            return int(default)

    def _threshold(self, value: int) -> None:
        self.threshold_value.setText(f"{value / 100:.2f}")
        self.settings.set("threshold", value / 100.0)

    def _cap_changed(self, key: str) -> None:
        self.cap_key = str(key)

    def _crop(self) -> None:
        self.signals.crop_requested.emit(self.cap_key)

    def retranslate_dynamic(self) -> None:
        pass


class DiscordPage(Page):
    STATUSES = (
        "ok",
        "invalid_url",
        "no_url",
        "network",
        "network_dns",
        "network_tls",
        "network_timeout",
        "network_blocked",
        "bad_request",
        "unauthorized",
        "forbidden",
        "not_found",
        "rate_limited",
        "server",
        "sending",
    )

    def __init__(self, theme: Theme, settings: Settings, signals: Signals, reporter, parent=None, support_opener=None):
        super().__init__(theme, parent)
        self.settings, self.signals, self.reporter = settings, signals, reporter
        self.support_opener = support_opener or open_support_invite
        self.toggles = {}
        self._busy = False
        self._status_key = ""
        self.add_title("nav_discord", "sub_discord")
        card = self.add_card()
        card.setObjectName("DiscordWebhookCard")
        card.body.addWidget(self.card_title("dm_card_title"))

        row = QHBoxLayout()
        row.setSpacing(10)
        label = self.text_label("dm_webhook_label")
        label.setMinimumWidth(110)
        row.addWidget(label)
        self.webhook_entry = QLineEdit()
        self.webhook_entry.setObjectName("DiscordWebhook")
        self.webhook_entry.setEchoMode(QLineEdit.Password)
        self.webhook_entry.setMinimumHeight(32)
        self.webhook_entry.setMinimumWidth(120)
        self.webhook_entry.setText(str(settings.get("discord_webhook_url", "") or ""))
        self.webhook_entry.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook_entry.textChanged.connect(self._webhook_changed)
        row.addWidget(self.webhook_entry, 1)
        self.reveal_button = RoundButton("", theme, "ghost")
        self.reveal_button.setObjectName("WebhookReveal")
        if TR is not None:
            TR.add(self.reveal_button, "dm_show", lambda w, txt: w.set_text(txt))
        else:
            self.reveal_button.set_text(i18n.t("en", "dm_show"))
        self.reveal_button.clicked.connect(self._reveal)
        row.addWidget(self.reveal_button)
        card.body.addLayout(row)

        self.test_button = RoundButton("", theme, "ghost")
        self.test_button.setObjectName("TestWebhookButton")
        if TR is not None:
            TR.add(self.test_button, "dm_test", lambda w, txt: w.set_text(txt))
        else:
            self.test_button.set_text(i18n.t("en", "dm_test"))
        self.test_button.clicked.connect(self._test)
        card.body.addWidget(self.test_button, 0, Qt.AlignLeft)

        self.status_label = QLabel()
        self.status_label.setObjectName("DMStatus")
        self.status_label.setProperty("role", "muted")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(16)
        card.body.addWidget(self.status_label)

        for key, label_key in (
            ("telemetry_enabled", "dm_enabled"),
            ("alert_enabled", "alert_check"),
            ("reward_shot_enabled", "dm_rshot"),
        ):
            toggle_row, toggle = self.toggle_row(settings, key, label_key, self._webhook_changed)
            self.toggles[key] = toggle
            card.body.addWidget(toggle_row)

        self.report_spin = self._double_spin(0, 24, 0.5, 1, self._number("report_hours", 0.0))
        self.report_spin.setObjectName("ReportHours")
        self.report_spin.valueChanged.connect(lambda v: self.settings.set("report_hours", float(v)))
        card.body.addWidget(self.spin_row("dm_every_pre", self.report_spin, "dm_every_post"))

        self.desc_label = self.text_label("dm_desc", muted=True, wrap=True, size=10)
        self.desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.body.addWidget(self.desc_label)
        self.help_label = self.text_label("dm_help", muted=True, wrap=True, size=10)
        self.help_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.body.addWidget(self.help_label)
        self.support_button = RoundButton("", theme, "ghost")
        self.support_button.setObjectName("SupportButton")
        self.support_button.setFixedHeight(36)
        self.support_button.setMinimumWidth(150)
        if TR is not None:
            TR.add(self.support_button, "support_join", lambda w, txt: w.set_text(txt))
        else:
            self.support_button.set_text(i18n.t("en", "support_join"))
        self.support_button.clicked.connect(lambda: self.support_opener(config.SUPPORT_INVITE))
        card.body.addWidget(self.support_button, 0, Qt.AlignLeft)
        self.outer.addWidget(card)
        self.outer.addStretch(1)

    def _double_spin(self, lo: float, hi: float, step: float, decimals: int, value: float) -> QDoubleSpinBox:
        spin = FocusDoubleSpinBox(self.theme)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        spin.setValue(float(value))
        return spin

    def _number(self, key: str, default: float) -> float:
        try:
            return float(self.settings.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _webhook_changed(self, _value=None) -> None:
        self.settings.set("discord_webhook_url", self.webhook_entry.text().strip())
        self.signals.webhook_changed.emit()

    def _reveal(self) -> None:
        hidden = self.webhook_entry.echoMode() == QLineEdit.Password
        self.webhook_entry.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        key = "dm_hide" if hidden else "dm_show"
        self.reveal_button.set_text(TR.t(key) if TR is not None else i18n.t("en", key))

    def _status_text(self, status: str) -> str:
        return TR.t("dm_s_" + status) if TR is not None else i18n.t("en", "dm_s_" + status)

    def _set_status(self, status: str) -> None:
        self._status_key = "dm_s_" + status
        self.status_label.setText(self._status_text(status))

    def _set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.test_button.setEnabled(not busy)

    def _test(self) -> None:
        if self._busy:
            return
        from discord_webhook import valid_webhook

        url = self.settings.get("discord_webhook_url", "") or ""
        if not str(url).strip():
            self._set_status("no_url")
            return
        if not valid_webhook(url):
            self._set_status("invalid_url")
            return
        self._set_busy(True)
        self._set_status("sending")
        self.reporter.send_test(lambda status: self.signals.discord_status.emit(status))

    def on_status(self, status: str) -> None:
        status = status if status in self.STATUSES else "server"
        self._set_busy(False)
        self._set_status(status)
        text = self._status_text(status)
        if status == "ok":
            self.signals.notify.emit(text, "success")
        elif status != "sending":
            self.signals.notify.emit(text, "error")

    def retranslate_dynamic(self) -> None:
        if self._status_key:
            self.status_label.setText(TR.t(self._status_key) if TR else "")
        key = "dm_hide" if self.webhook_entry.echoMode() == QLineEdit.Normal else "dm_show"
        self.reveal_button.set_text(TR.t(key) if TR else i18n.t("en", key))


class ExtrasPage(Page):
    def __init__(self, theme: Theme, settings: Settings, signals: Signals, parent=None, opener=None):
        super().__init__(theme, parent)
        self.settings, self.signals, self.opener = settings, signals, opener
        self.toggles = {}
        self.spins = {}
        self.add_title("nav_extras", "sub_extras")
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ExtrasScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content = QWidget()
        self.content.setObjectName("ExtrasContent")
        self.content.setAttribute(Qt.WA_TranslucentBackground)
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        self.outer.addWidget(self.scroll, 1)
        self.apply_theme()

        snd = self._card("AudioCard")
        snd.body.addWidget(self.card_title("sec_audio"))
        for key, label in (
            ("auto_mute_enabled", "ex_mute"),
            ("afk_mouse_look", "ex_look"),
            ("humanizer_enabled", "ex_human"),
            ("jitter_enabled", "ex_jitter"),
        ):
            row, toggle = self.toggle_row(settings, key, label, self._refresh_preview)
            self.toggles[key] = toggle
            snd.body.addWidget(row)
        pct = FocusSpinBox(self.theme)
        pct.setRange(5, 50)
        pct.setKeyboardTracking(False)
        pct.setValue(max(5, min(50, int(round(float(settings.get("wait_jitter_percent", 0.15)) * 100)))))
        pct.setObjectName("JitterPercent")
        pct.valueChanged.connect(self._on_jitter)
        self.spins["wait_jitter_percent"] = pct
        snd.body.addWidget(self._inline_spin("ex_jpct_pre", pct, "ex_jpct_post"))
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setProperty("role", "muted")
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        snd.body.addWidget(self.preview_label)
        self._refresh_preview()

        auto = self._card("AutomationCard")
        auto.body.addWidget(self.card_title("sec_automation"))
        for key, label in (
            ("loot_vault_enabled", "ex_loot"),
            ("mode_fix_enabled", "ex_modefix"),
            ("bus_drop_enabled", "ex_bus"),
            ("pickaxe_afk_enabled", "ex_pickaxe"),
            ("coffee_break_enabled", "ex_coffee"),
            ("auto_calibrate", "ex_calib"),
        ):
            row, toggle = self.toggle_row(settings, key, label, self._refresh_preview)
            self.toggles[key] = toggle
            auto.body.addWidget(row)
            if key == "loot_vault_enabled":
                auto.body.addWidget(self._reward_button_row())
        dive = self._number_spin("bus_dive_seconds", 1, 60, 1, 0)
        dive.valueChanged.connect(lambda v: settings.set("bus_dive_seconds", float(v)))
        self.spins["bus_dive_seconds"] = dive
        auto.body.addWidget(self._inline_spin("ex_dive_pre", dive, "ex_dive_post"))
        pmin = self._number_spin("pickaxe_min_s", 1, 3600, 5, 0)
        pmin.valueChanged.connect(lambda v: settings.set("pickaxe_min_s", float(v)))
        self.spins["pickaxe_min_s"] = pmin
        pmax = self._number_spin("pickaxe_max_s", 1, 3600, 5, 0)
        pmax.valueChanged.connect(lambda v: settings.set("pickaxe_max_s", float(v)))
        self.spins["pickaxe_max_s"] = pmax
        auto.body.addWidget(self._inline_spin("ex_pick_pre", pmin, "ex_pick_post", mid_key="ex_pick_mid", second=pmax))

        net = self._card("NetworkCard")
        net.body.addWidget(self.card_title("sec_network"))
        for key, label in (
            ("squad_check_enabled", "ex_squad"),
            ("auto_relaunch_enabled", "ex_relaunch"),
            ("auto_relaunch_freeze_enabled", "ex_relaunch_freeze"),
            ("web_remote_enabled", "ex_web_remote"),
            ("web_remote_tunnel", "ex_web_tunnel"),
        ):
            row, toggle = self.toggle_row(settings, key, label, self._refresh_preview)
            self.toggles[key] = toggle
            net.body.addWidget(row)
            if key == "web_remote_tunnel":
                toggle.toggled.connect(self.signals.tunnel_requested.emit)
            if key == "web_remote_enabled":
                toggle.toggled.connect(self.signals.web_remote_requested.emit)
            if key == "squad_check_enabled":
                stuck = self._number_spin("stuck_timeout_min", 0, 240, 5, 0)
                stuck.valueChanged.connect(lambda v: settings.set("stuck_timeout_min", float(v)))
                self.spins["stuck_timeout_min"] = stuck
                net.body.addWidget(self._inline_spin("ex_stuck_pre", stuck, "ex_stuck_post", post_wrap=True))

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._refresh_preview)
        settings.changed.connect(self._on_setting)

    def _card(self, name: str) -> Card:
        card = self.add_card()
        card.setObjectName(name)
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        return card

    def _number_spin(self, key: str, lo: float, hi: float, step: float, decimals: int) -> QDoubleSpinBox:
        spin = FocusDoubleSpinBox(self.theme)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        spin.setValue(float(self._number(key, lo)))
        spin.setObjectName("Spin_" + key)
        return spin

    def _number(self, key: str, default: float) -> float:
        try:
            return float(self.settings.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _inline_spin(
        self,
        pre_key: str,
        spin,
        post_key: str,
        mid_key: str = "",
        second=None,
        indent: int = 12,
        post_wrap: bool = False,
    ) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(indent, 0, 0, 0)
        lay.setSpacing(6)
        pre = self.text_label(pre_key, muted=True, wrap=False)
        pre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        spin.setMinimumHeight(30)
        lay.addWidget(pre)
        lay.addWidget(spin)
        if second is not None:
            mid = self.text_label(mid_key, muted=True, wrap=False)
            second.setMinimumHeight(30)
            lay.addWidget(mid)
            lay.addWidget(second)
        post = self.text_label(post_key, muted=True, wrap=post_wrap)
        post.setSizePolicy(QSizePolicy.Expanding if post_wrap else QSizePolicy.Preferred, QSizePolicy.Preferred)
        lay.addWidget(post)
        if not post_wrap:
            lay.addStretch(1)
        return row

    def _reward_button_row(self) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 0, 0, 0)
        button = RoundButton("", self.theme, "ghost")
        button.setObjectName("RewardsFolderButton")
        if TR is not None:
            TR.add(button, "ex_loot_open", lambda w, txt: w.set_text(txt))
        else:
            button.set_text(i18n.t("en", "ex_loot_open"))
        button.clicked.connect(self._open_rewards)
        self.rewards_button = button
        lay.addWidget(button)
        lay.addStretch(1)
        return row

    def _on_jitter(self, value: int) -> None:
        self.settings.set("wait_jitter_percent", max(5, min(50, int(value))) / 100.0)

    def _on_setting(self, *_args) -> None:
        self._refresh_preview()

    def _refresh_preview(self, *_args) -> None:
        if not hasattr(self, "preview_label"):
            return
        mode = str(self.settings.get("mode", "A"))
        key = {"B": "wait_b", "C": "wait_c"}.get(mode, "afk_interval")
        base = self._number(key, 10.0)
        enabled = bool(self.settings.get("jitter_enabled", True))
        pct = max(0.0, min(0.5, self._number("wait_jitter_percent", 0.15)))
        if enabled:
            lo, hi = base * (1.0 - pct), base * (1.0 + pct)
            text = (
                TR.t("ex_jprev", base=base, lo=lo, hi=hi) if TR else i18n.t("en", "ex_jprev", base=base, lo=lo, hi=hi)
            )
        else:
            text = TR.t("ex_jprev_off", base=base) if TR else i18n.t("en", "ex_jprev_off", base=base)
        self.preview_label.setText(text)

    def _open_rewards(self) -> None:
        try:
            from loot_vault import LootVault

            folder = LootVault().folder
            os.makedirs(folder, exist_ok=True)
            ok = self._open_path(folder)
        except Exception:
            ok = False
        if not ok:
            self.signals.notify.emit("loot_vault: could not open the folder", "error")

    def _open_path(self, path: str) -> bool:
        if self.opener is not None:
            return bool(self.opener(path))
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(path)))

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if hasattr(self, "timer"):
            self.timer.start()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        if hasattr(self, "timer"):
            self.timer.stop()

    def retranslate_dynamic(self) -> None:
        self._refresh_preview()

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.scroll.setStyleSheet(
            f"QScrollArea#ExtrasScroll {{ background: transparent; border: none; }}"
            f"QWidget#ExtrasContent {{ background: transparent; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {t['EDGE']}; min-height: 34px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {t['ACCENT']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"
        )


class LogPage(Page):
    unread_changed = Signal(int)
    LINE_LIMIT = 0

    def __init__(self, theme: Theme, signals: Signals, parent=None, opener=None):
        super().__init__(theme, parent)
        self.signals, self.opener = signals, opener
        self.active = False
        self.unread = 0
        self.recent = deque(maxlen=5)
        self._status_live = False
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)
        self.add_title("nav_log", "sub_log")
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.copy_button = RoundButton("", theme, "ghost")
        self.clear_button = RoundButton("", theme, "ghost")
        self.folder_button = RoundButton("", theme, "ghost")
        for button, key, slot in (
            (self.copy_button, "log_copy", self._copy),
            (self.clear_button, "log_clear", self._clear),
            (self.folder_button, "log_folder", self._open_folder),
        ):
            if TR is not None:
                TR.add(button, key, lambda w, txt: w.set_text(txt))
            else:
                button.set_text(i18n.t("en", key))
            button.clicked.connect(slot)
            lay.addWidget(button)
        self.status = QLabel()
        self.status.setProperty("role", "muted")
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.outer.addWidget(bar)
        self.view = QPlainTextEdit()
        self.view.setObjectName("LogView")
        self.view.setReadOnly(True)
        self.view.setUndoRedoEnabled(False)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setMaximumBlockCount(self.LINE_LIMIT)
        self.view.setFocusPolicy(Qt.ClickFocus)
        self.view.setFont(QFont("Consolas", 9))
        self.outer.addWidget(self.view, 1)
        self.apply_theme()

    def append_line(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        bar = self.view.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 2
        self.view.appendPlainText(line)
        self.recent.append(line[:160])
        if follow:
            bar.setValue(bar.maximum())
        if not self.active:
            self.unread = min(99, self.unread + 1)
            self.unread_changed.emit(self.unread)

    def set_active(self, active: bool) -> None:
        self.active = bool(active)
        if self.active:
            self.mark_read()

    def mark_read(self) -> None:
        if self.unread != 0:
            self.unread = 0
            self.unread_changed.emit(0)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.view.toPlainText())
        self._status_live = True
        self.status.setText(TR.t("log_copied") if TR else i18n.t("en", "log_copied"))
        self._status_timer.start(1600)

    def _clear(self) -> None:
        self.view.clear()
        self.recent.clear()
        self.mark_read()

    def _clear_status(self) -> None:
        self._status_live = False
        self.status.clear()

    def _open_folder(self) -> None:
        try:
            ok = self._open_path(config.base_dir())
        except Exception:
            ok = False
        if not ok:
            self.signals.notify.emit("open folder: OSError", "error")

    def _open_path(self, path: str) -> bool:
        if self.opener is not None:
            return bool(self.opener(path))
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(path)))

    def retranslate_dynamic(self) -> None:
        if self._status_live:
            self.status.setText(TR.t("log_copied") if TR else i18n.t("en", "log_copied"))

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.view.setStyleSheet(
            f"QPlainTextEdit#LogView {{ background: {t['INSET']}; color: {t['TEXT']}; "
            f"border: 1px solid {t['EDGE']}; border-radius: 12px; padding: 10px; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {t['EDGE']}; min-height: 34px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {t['ACCENT']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"
        )


class GuidePage(Page):
    def __init__(self, theme: Theme, parent=None, support_opener=None):
        super().__init__(theme, parent)
        self.support_opener = support_opener or open_support_invite
        self.add_title("nav_guide", "sub_guide")
        self.view = QTextBrowser()
        self.view.setObjectName("GuideView")
        self.view.setReadOnly(True)
        self.view.setOpenExternalLinks(False)
        self.view.setOpenLinks(False)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.outer.addWidget(self.view, 1)
        self.support_button = RoundButton("", theme, "ghost")
        self.support_button.setObjectName("GuideSupportButton")
        self.support_button.setFixedHeight(36)
        self.support_button.setMinimumWidth(150)
        if TR is not None:
            TR.add(self.support_button, "support_join", lambda w, txt: w.set_text(txt))
        else:
            self.support_button.set_text(i18n.t("en", "support_join"))
        self.support_button.clicked.connect(lambda: self.support_opener(config.SUPPORT_INVITE))
        self.outer.addWidget(self.support_button, 0, Qt.AlignLeft)
        self.apply_theme()

    def render(self) -> None:
        lang = TR.lang if TR is not None else "en"
        parts = []
        for kind, text in i18n.guide(lang):
            safe = html.escape(str(text), quote=False)
            if kind == "h1":
                parts.append(f'<p class="h1">{safe}</p>')
            elif kind == "h2":
                parts.append(f'<p class="h2">{safe}</p>')
            elif kind == "li":
                parts.append(f'<p class="li">•&nbsp;&nbsp;{safe}</p>')
            else:
                parts.append(f'<p class="n">{safe}</p>')
        family_name = "Yu Gothic UI" if lang == "ja" else "Segoe UI"
        css = (
            f'body {{ color: {self.theme.tokens["TEXT"]}; font-family: "{family_name}", Inter; '
            f"font-size: 10pt; }}\n"
            "p.h1 { font-size: 15px; font-weight: 600; margin: 14px 0 6px 0; }\n"
            "p.h2 { font-size: 11px; font-weight: 600; margin: 10px 0 4px 0; }\n"
            "p { margin: 2px 0 4px 0; }\n"
            "p.n { margin-left: 12px; }\n"
            "p.li { margin-left: 26px; text-indent: -14px; }\n"
        )
        self.view.document().setDefaultStyleSheet(css)
        self.view.setHtml("".join(parts))
        self.view.verticalScrollBar().setValue(0)

    def retranslate_dynamic(self) -> None:
        self.render()

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.view.setStyleSheet(
            f"QTextBrowser#GuideView {{ background: {t['INSET']}; color: {t['TEXT']}; "
            f"border: 1px solid {t['EDGE']}; border-radius: 12px; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {t['EDGE']}; min-height: 34px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {t['ACCENT']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"
        )
        self.view.document().setDocumentMargin(14)
        self.render()


class ReportNotice(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._kind = ""
        self._path = ""
        self._text = ""
        self._error = ""
        self.setObjectName("ReportNotice")
        self.setStyleSheet(
            f"QWidget#ReportNotice {{ background: {theme.tokens['FIELD']}; border: 1px solid {theme.tokens['EDGE']}; border-radius: 12px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        self.title = QLabel()
        self.title.setStyleSheet(f"font-size:15px; font-weight:600; color:{theme.tokens['TEXT']};")
        lay.addWidget(self.title)
        self.path = QLabel()
        self.path.setStyleSheet(f"font-size:10px; color:{theme.tokens['MUTED']};")
        self.path.setWordWrap(True)
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.path)
        self.preview = QLabel()
        self.preview.setStyleSheet(f"font-size:10px; color:{theme.tokens['TEXT']};")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.copy = RoundButton("", theme, "ghost")
        self.copy.setFixedHeight(30)
        self.copy.clicked.connect(self._copy)
        if TR is not None:
            TR.add(self.copy, "log_copy", lambda w, txt: w.set_text(txt))
        else:
            self.copy.set_text("Copy")
        row.addWidget(self.copy)
        row.addStretch(1)
        lay.addLayout(row)
        self.hide()

    def show_result(self, kind: str, path: str, text: str, error: str = "") -> None:
        self._kind, self._path, self._text, self._error = kind, path, text, error
        self.retranslate()
        if error:
            self.preview.setText(error[:600])
            self.copy.setVisible(False)
        else:
            lines = [ln for ln in text.splitlines()[:3] if ln.strip()]
            self.preview.setText("\n".join(lines)[:600])
            self.copy.setVisible(bool(text))
        self.show()

    def retranslate(self) -> None:
        if not self._kind:
            return
        title_key = "diag_title" if self._kind == "diag" else "ac_title"
        self.title.setText(TR.t(title_key) if TR else ("Diagnostics" if self._kind == "diag" else "Auto-check result"))
        if self._path:
            self.path.setVisible(True)
            self.path.setText((TR.t("log_saved", path=self._path) if TR else "Saved: " + self._path))
        else:
            self.path.setVisible(False)
        if self._error:
            if self._kind == "diag":
                self.path.setText(TR.t("diag_failed") if TR else "Diagnosis failed")
                self.path.setVisible(True)
            else:
                self.path.setVisible(False)

    def _copy(self) -> None:
        if not self._text:
            return
        QApplication.clipboard().setText(self._text)
        self.copy.set_text(TR.t("log_copied") if TR else "Copied")
        QTimer.singleShot(1200, self._reset_copy)

    def _reset_copy(self) -> None:
        self.copy.set_text(TR.t("log_copy") if TR else "Copy")


class ToolsPage(Page):
    def __init__(self, theme: Theme, settings: Settings, signals: Signals, parent=None):
        super().__init__(theme, parent)
        self.settings, self.signals = settings, signals
        self.add_title("nav_tools", "sub_tools")
        diag = self.add_card()
        dtitle = QLabel()
        dtitle.setStyleSheet(f"font-size:15px; font-weight:600; color:{theme.tokens['TEXT']};")
        diag.body.addWidget(dtitle)
        if TR is not None:
            TR.add(dtitle, "diag_title")
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tool_buttons = {}
        self._diag_busy = False
        self._ac_busy = False
        for i, key in enumerate(("diag_button", "ac_button", "hud_button", "remote_button")):
            b = RoundButton("", theme, "ghost")
            b.setFixedHeight(38)
            if TR is not None:
                TR.add(b, key, lambda w, txt: w.set_text(txt))
            else:
                b.set_text(EN[key])
            b.clicked.connect(lambda _=False, k=key: self._tool_clicked(k))
            self.tool_buttons[key] = b
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        diag.body.addLayout(grid)
        remote_row, self.remote_autostart = self.toggle_row(settings, "phone_remote_autostart", "rm_autostart")
        diag.body.addWidget(remote_row)
        self.notice = ReportNotice(theme)
        diag.body.addWidget(self.notice)
        self.admin_button = RoundButton("", theme, "ghost")
        if TR is not None:
            TR.add(self.admin_button, "admin_button", lambda w, txt: w.set_text(txt))
        self.admin_button.clicked.connect(self._admin)
        diag.body.addWidget(self.admin_button, 0, Qt.AlignLeft)
        self.signals.tool_result.connect(self._tool_done)
        self.outer.addWidget(diag)
        look = self.add_card()
        title = QLabel()
        title.setStyleSheet(f"font-size:15px; font-weight:600; color:{theme.tokens['TEXT']};")
        look.body.addWidget(title)
        if TR is not None:
            TR.add(title, "look_title")
        theme_lab = QLabel()
        look.body.addWidget(theme_lab)
        if TR is not None:
            TR.add(theme_lab, "look_theme")
        trow = QHBoxLayout()
        trow.setSpacing(10)
        self.tiles = []
        for name in THEME_ORDER:
            tile = ThemeTile(name, theme)
            tile.picked.connect(self._pick)
            self.tiles.append(tile)
            trow.addWidget(tile)
        trow.addStretch(1)
        look.body.addLayout(trow)
        op_lab = QLabel()
        look.body.addWidget(op_lab)
        if TR is not None:
            TR.add(op_lab, "look_opacity")
        orow = QHBoxLayout()
        stored = settings.get("ui_opacity", None)
        op = (
            int(round(float(stored) * 100))
            if isinstance(stored, (int, float)) and float(stored) <= 1.0
            else (int(stored) if stored is not None else 100)
        )
        op = max(30, min(100, op))
        self.slider = Slider(theme, 30, 100, op)
        self.pct = QLabel(f"{op} %")
        self.pct.setMinimumWidth(44)
        self.slider.valueChanged.connect(self._opacity)
        orow.addWidget(self.slider, 1)
        orow.addWidget(self.pct)
        look.body.addLayout(orow)
        self.outer.addWidget(look)
        upd = self.add_card()
        utitle = QLabel()
        utitle.setStyleSheet(f"font-size:15px; font-weight:600; color:{theme.tokens['TEXT']};")
        upd.body.addWidget(utitle)
        if TR is not None:
            TR.add(utitle, "upd_ver", lambda w, txt: w.setText(txt), {"cur": APP_VERSION})
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        upd.body.addWidget(self.update_status)
        self.update_status.hide()
        self.update_auto = Toggle(theme)
        self.update_auto.set_on(bool(settings.get("auto_update_check", False)))
        self.update_auto.toggled.connect(lambda v: settings.set("auto_update_check", bool(v)))
        self.update_check = RoundButton("", theme, "ghost")
        if TR is not None:
            TR.add(self.update_check, "upd_check", lambda w, txt: w.set_text(txt))
        self.update_check.clicked.connect(self._update_click)
        if UPDATE_REPO:
            urow = QHBoxLayout()
            urow.addWidget(self.update_auto)
            ualabel = QLabel()
            urow.addWidget(ualabel, 1)
            if TR is not None:
                TR.add(ualabel, "upd_auto")
            urow.addWidget(self.update_check)
            upd.body.addLayout(urow)
        else:
            self.update_auto.hide()
            self.update_check.hide()
        self.update_service = UpdateService(
            settings,
            on_state=self._update_state,
            log=lambda m: signals.log_line.emit(m),
            on_available=self._update_available,
        )
        self.outer.addStretch(1)
        self._apply(op)

    def _tool_clicked(self, key: str) -> None:
        if key == "diag_button":
            self._run_diag()
        elif key == "ac_button":
            self._run_autocheck()
        elif key == "hud_button":
            self.signals.hud_requested.emit()
        elif key == "remote_button":
            self.signals.remote_requested.emit()

    def _admin(self) -> None:
        if app_support.is_admin():
            self.signals.notify.emit("Already running as administrator", "info")
        elif not app_support.relaunch_as_admin():
            self.signals.notify.emit(TR.t("admin_failed") if TR else "Could not request administrator rights", "error")

    def _update_click(self) -> None:
        if not UPDATE_REPO:
            return
        if not self.update_service.check():
            self.update_status.setText(TR.t("upd_check_failed") if TR else "Could not check")
            self.update_status.show()

    def _update_state(self, kind: str, info=None) -> None:
        key = {"checking": "upd_checking", "latest": "upd_latest", "failed": "upd_check_failed", "dev": "upd_dev"}.get(
            kind
        )
        if kind == "available" and info is not None:
            self._update_available(info)
            return
        if key:
            self.update_status.setText(TR.t(key) if TR else key)
            self.update_status.show()

    def _update_available(self, info) -> None:
        text = (
            TR.t("upd_newver", new=info.latest_version, cur=APP_VERSION) if TR else f"New version {info.latest_version}"
        )
        url = getattr(info, "page_url", "") or getattr(info, "download_url", "")
        self.update_status.setText(f"{text} {url}".strip())
        self.update_status.show()
        self.signals.notify.emit(f"{text} {url}".strip(), "info")

    def _begin_tool(self, kind: str) -> None:
        if kind == "diag":
            self._diag_busy = True
            key, running = "diag_button", "diag_running"
        else:
            self._ac_busy = True
            key, running = "ac_button", "ac_running"
        self.notice.hide()
        b = self.tool_buttons[key]
        b.setEnabled(False)
        b.set_text(TR.t(running) if TR else ("Running…" if kind == "diag" else "Checking…"))

    def _finish_tool(self, kind: str) -> None:
        if kind == "diag":
            self._diag_busy = False
            key = "diag_button"
        else:
            self._ac_busy = False
            key = "ac_button"
        b = self.tool_buttons[key]
        b.setEnabled(True)
        b.set_text(TR.t(key) if TR else EN[key])

    def _run_diag(self) -> None:
        if self._diag_busy:
            return
        self._begin_tool("diag")
        try:
            import diagnose

            path = diagnose.default_report_path()
        except Exception as e:
            self._tool_done("diag", "", "", f"{type(e).__name__}: {e}")
            return
        threading.Thread(target=self._diag_work, args=(path,), daemon=True, name="FNauto-diagnose").start()

    def _diag_work(self, path: str) -> None:
        try:
            import diagnose

            diagnose.run(path)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.signals.tool_result.emit("diag", path, text, "")
        except Exception as e:
            self.signals.tool_result.emit("diag", path, "", f"{type(e).__name__}: {e}")

    def _run_autocheck(self) -> None:
        if self._ac_busy:
            return
        self._begin_tool("ac")
        try:
            import autocheck

            path = autocheck.default_report_path()
        except Exception as e:
            self._tool_done("ac", "", "", f"{type(e).__name__}: {e}")
            return
        lang = TR.lang if TR else "en"
        threading.Thread(target=self._autocheck_work, args=(path, lang), daemon=True, name="FNauto-autocheck").start()

    def _autocheck_work(self, path: str, lang: str) -> None:
        try:
            import autocheck
            from controller import SettingsAdapter

            text = autocheck.run_report(SettingsAdapter(self.settings), path, lang)
            self.signals.tool_result.emit("ac", path, text, "")
        except Exception as e:
            self.signals.tool_result.emit("ac", path, "", f"{type(e).__name__}: {e}")

    def _tool_done(self, kind: str, path: str, text: str, error: str) -> None:
        self._finish_tool(kind)
        self.notice.show_result(kind, path, text, error)
        if error:
            if kind == "diag":
                msg = (TR.t("diag_failed") if TR else "Diagnosis failed") + ": " + error
            else:
                msg = (TR.t("ac_title") if TR else "Auto-check result") + ": " + error
            notify_kind = "error"
        else:
            msg = TR.t("log_saved", path=path) if TR else "Saved: " + path
            notify_kind = "warning" if ("⚠" in text or "warning" in text.lower()) else "success"
        self.signals.notify.emit(msg, notify_kind)

    def retranslate_dynamic(self) -> None:
        self.notice.retranslate()
        if self._diag_busy:
            self.tool_buttons["diag_button"].set_text(TR.t("diag_running") if TR else "Running…")
        if self._ac_busy:
            self.tool_buttons["ac_button"].set_text(TR.t("ac_running") if TR else "Checking…")

    def _opacity(self, v: int) -> None:
        self.pct.setText(f"{v} %")
        self.settings.set("ui_opacity", round(v / 100.0, 2))
        self._apply(v)

    def _apply(self, v: int) -> None:
        self.signals.opacity.emit(v)

    def _pick(self, name: str) -> None:
        self.settings.set("ui_theme", name)


NOTIF_STYLE = "popover"
NOTIF_W = 360
NOTIF_PAD = 16
NOTIF_HEADER = 52
NOTIF_GAP = 8
NOTIF_MIN_H = 170
NOTIF_MAX_H = 440
_NOTIF_KIND = {
    "ok": "success",
    "success": "success",
    "info": "info",
    "warning": "warning",
    "warn": "warning",
    "error": "error",
    "bad": "error",
}


def _notif_kind(kind: str) -> str:
    return _NOTIF_KIND.get(str(kind).lower(), "info")


def _notif_color(theme: Theme, kind: str) -> QColor:
    key = {"success": "GOOD", "warning": "ACCENT_HI", "error": "DANGER"}.get(kind, "ACCENT")
    if kind == "warning":
        return QColor("#F5A524")
    return theme.c(key)


def _draw_notif_symbol(p: QPainter, kind: str, rect: QRectF, color: QColor) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    cx, cy = rect.center().x(), rect.center().y()
    if kind == "success":
        path = QPainterPath(QPointF(rect.left() + 5, cy))
        path.lineTo(rect.center().x() - 1, rect.bottom() - 6)
        path.lineTo(rect.right() - 5, rect.top() + 6)
        p.drawPath(path)
    elif kind == "warning":
        path = QPainterPath(QPointF(cx, rect.top() + 4))
        path.lineTo(rect.right() - 4, rect.bottom() - 4)
        path.lineTo(rect.left() + 4, rect.bottom() - 4)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(cx, cy - 3), QPointF(cx, cy + 3))
        p.drawPoint(QPointF(cx, cy + 7))
    elif kind == "error":
        p.drawLine(QPointF(rect.left() + 5, rect.top() + 5), QPointF(rect.right() - 5, rect.bottom() - 5))
        p.drawLine(QPointF(rect.right() - 5, rect.top() + 5), QPointF(rect.left() + 5, rect.bottom() - 5))
    else:
        p.drawEllipse(QRectF(cx - 2, rect.top() + 4, 4, 4))
        p.drawLine(QPointF(cx, cy), QPointF(cx, rect.bottom() - 5))
    p.restore()


class NotifScrim(QWidget):
    clicked = Signal()
    SCRIM_ALPHA = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opacity = 0.0
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCursor(Qt.ArrowCursor)
        self.hide()

    def paintEvent(self, _e) -> None:

        return

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        e.accept()


class NotifIconButton(QWidget):
    clicked = Signal()

    def __init__(self, kind: str, theme: Theme, size: int = 18, parent=None):
        super().__init__(parent)
        self.kind, self.theme, self.size = kind, theme, size
        self.hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = self.theme.c("TEXT" if self.hover else "MUTED")
        if self.hover:
            p.setPen(Qt.NoPen)
            p.setBrush(self.theme.c("HOVER"))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 5, 5)
        p.setPen(QPen(col, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if self.kind == "copy":
            p.drawRoundedRect(QRectF(5, 7, 8, 8), 1.5, 1.5)
            p.drawRoundedRect(QRectF(8, 4, 8, 8), 1.5, 1.5)
        else:
            p.drawLine(QPointF(5, 5), QPointF(13, 13))
            p.drawLine(QPointF(13, 5), QPointF(5, 13))
        p.end()


class ClearAllButton(QWidget):
    clicked = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.hover = False
        self.text = TR.t("notif_clear") if TR else "Clear all"
        self.tip = TR.t("notif_clear_tip") if TR else "Clear all notifications"
        self.setFixedHeight(32)
        self._fit()
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.tip)

    def _fit(self) -> None:
        fm = QFontMetrics(QFont(family(True), 8))
        self.setFixedWidth(32 + 6 + fm.horizontalAdvance(self.text) + 2)

    def set_text(self, text: str, tip: str) -> None:
        self.text, self.tip = text, tip
        self._fit()
        self.setToolTip(tip)
        self.setAccessibleName(text)
        self.update()

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("HOVER" if self.hover else "FIELD"))
        p.drawRoundedRect(QRectF(0.5, 0.5, 31, 31), 8, 8)
        p.setPen(QPen(t.c("TEXT" if self.hover else "MUTED"), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(21, 9), QPointF(14, 16))
        p.drawLine(QPointF(14, 16), QPointF(10, 14))
        p.drawLine(QPointF(10, 14), QPointF(8, 17))
        p.drawLine(QPointF(8, 17), QPointF(15, 24))
        p.drawLine(QPointF(15, 24), QPointF(18, 22))
        p.drawLine(QPointF(18, 22), QPointF(14, 16))
        p.setPen(t.c("TEXT" if self.hover else "MUTED"))
        p.setFont(QFont(family(True), 8))
        p.drawText(QRectF(38, 0, self.width() - 38, 32), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        p.end()


class NotificationCopyButton(QWidget):
    clicked = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.hover = False
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        if self.hover:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("HOVER"))
            p.drawRoundedRect(QRectF(0, 0, 28, 28), 7, 7)
        col = t.c("TEXT" if self.hover else "MUTED")
        p.setPen(QPen(col, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(8, 10, 9, 9), 2, 2)
        p.drawRoundedRect(QRectF(11, 7, 9, 9), 2, 2)
        p.end()


class NotificationEntry(QWidget):
    copied = Signal(str)
    dismissed = Signal(object)

    PAD_X = 12
    PAD_Y = 10
    ICON = 32
    COPY = 28
    TITLE_H = 18
    META_H = 15
    META_GAP = 4
    DETAIL_GAP = 2
    MIN_H = 52

    def __init__(self, note, theme: Theme, parent=None):
        super().__init__(parent)
        self.note = note
        self.time, self.text, self.raw_kind = note
        self.kind = _notif_kind(self.raw_kind)
        self.theme = theme
        self.hover = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.MIN_H)
        self.setMouseTracking(True)
        raw = str(self.text).replace(chr(13), "")
        if chr(10) in raw:
            self.title_text, self.detail_text = (part.strip() for part in raw.split(chr(10), 1))
        elif len(raw) > 64 and " " in raw[:64]:
            cut = raw.rfind(" ", 0, 64)
            self.title_text, self.detail_text = raw[:cut], raw[cut:].strip()
        elif len(raw) > 64:
            self.title_text, self.detail_text = raw[:64], raw[64:]
        else:
            self.title_text, self.detail_text = raw, ""
        self.detail_layout = None
        self.detail_lines = 0
        self.detail_elided = False
        self.title_rect = QRectF()
        self.detail_rect = QRectF()
        self.meta_rect = QRectF()
        self.copy = NotificationCopyButton(theme, self)
        self.copy.setToolTip(TR.t("notif_copy") if TR else "Copy")
        self.copy.clicked.connect(self._copy)
        self.dismiss = NotifIconButton("close", theme, 18, self)
        self.dismiss.setToolTip(TR.t("notif_dismiss") if TR else "Dismiss")
        self.dismiss.clicked.connect(lambda: self.dismissed.emit(self.note))
        self.dismiss.hide()
        self._recalc(328)

    def _font(self, px: int, bold: bool = False) -> QFont:
        font = QFont(family(bold))
        font.setPixelSize(px)
        font.setWeight(QFont.DemiBold if bold else QFont.Normal)
        return font

    def _measure_detail(self, width: float) -> None:
        self.detail_layout = None
        self.detail_lines = 0
        self.detail_elided = False
        if not self.detail_text:
            return
        text_w = max(40.0, width - self.PAD_X - self.ICON - 10 - self.COPY - self.PAD_X - 8)
        layout = QTextLayout(self.detail_text, self._font(12))
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0.0
        for _ in range(3):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(text_w)
            line.setPosition(QPointF(0, y))
            y += line.height()
            self.detail_lines += 1

        extra = layout.createLine()
        self.detail_elided = bool(extra.isValid())
        layout.endLayout()
        self.detail_layout = layout

    def _recalc(self, width: float) -> None:
        width = max(120, int(width))
        self._measure_detail(width)
        text_w = max(40.0, width - self.PAD_X - self.ICON - 10 - self.COPY - self.PAD_X - 8)
        detail_h = 0.0
        if self.detail_layout is not None:
            detail_h = 0.0
            for i in range(self.detail_lines):
                detail_h += self.detail_layout.lineAt(i).height()
        height = self.PAD_Y * 2 + self.TITLE_H
        if self.detail_layout is not None:
            height += self.DETAIL_GAP + detail_h
        height += self.META_GAP + self.META_H
        height = max(self.MIN_H, int(round(height)))
        if height != self.height():
            self.setFixedHeight(height)
        x_text = self.PAD_X + self.ICON + 10
        self.title_rect = QRectF(x_text, self.PAD_Y, text_w, self.TITLE_H)
        detail_y = self.PAD_Y + self.TITLE_H + self.DETAIL_GAP
        self.detail_rect = QRectF(x_text, detail_y, text_w, detail_h)
        meta_y = detail_y + (detail_h + self.META_GAP if self.detail_layout is not None else self.META_GAP)
        self.meta_rect = QRectF(x_text, meta_y, text_w, self.META_H)
        self.copy.move(width - self.PAD_X - self.COPY, (height - self.COPY) // 2)
        self.dismiss.move(width - self.PAD_X - 18, 4)
        self.updateGeometry()
        self.update()

    def resizeEvent(self, _e) -> None:
        self._recalc(self.width())

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.dismiss.show()
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.dismiss.hide()
        self.update()

    def _copy(self) -> None:
        QApplication.clipboard().setText(str(self.text))
        self.copied.emit(str(self.text))

    def _category(self) -> str:
        key = "notif_cat_" + self.kind
        return TR.t(key) if TR else self.kind.capitalize()

    def retranslate(self) -> None:
        self.copy.setToolTip(TR.t("notif_copy") if TR else "Copy")
        self.dismiss.setToolTip(TR.t("notif_dismiss") if TR else "Dismiss")
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("HOVER" if self.hover else "TILE"))
        p.drawRoundedRect(rect, 10, 10)

        col = _notif_color(t, self.kind)
        tile = QColor(col)
        tile.setAlpha(38)
        tile_y = (self.height() - self.ICON) / 2
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 95), 1))
        p.setBrush(tile)
        p.drawRoundedRect(QRectF(self.PAD_X, tile_y, self.ICON, self.ICON), 9, 9)
        _draw_notif_symbol(
            p,
            self.kind,
            QRectF(self.PAD_X + (self.ICON - 18) / 2, tile_y + (self.ICON - 18) / 2, 18, 18),
            col,
        )

        p.setPen(t.c("TEXT"))
        p.setFont(self._font(13, True))
        title = p.fontMetrics().elidedText(self.title_text, Qt.ElideRight, int(self.title_rect.width()))
        p.drawText(self.title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        if self.detail_layout is not None:
            p.save()
            p.setClipRect(self.detail_rect)
            p.setPen(t.c("MUTED"))
            p.setFont(self._font(12))
            self.detail_layout.draw(p, QPointF(self.detail_rect.left(), self.detail_rect.top()))
            if self.detail_elided and self.detail_lines:
                last = self.detail_layout.lineAt(self.detail_lines - 1)
                end_x = self.detail_rect.left() + last.naturalTextWidth() - 2
                p.drawText(QPointF(end_x, self.detail_rect.bottom() - 3), "…")
            p.restore()

        p.setPen(t.c("MUTED"))
        p.setFont(self._font(11))
        meta = p.fontMetrics().elidedText(
            f"{self.time}  ·  {self._category()}", Qt.ElideRight, int(self.meta_rect.width())
        )
        p.drawText(self.meta_rect, Qt.AlignLeft | Qt.AlignVCenter, meta)
        p.end()


class NotifToday(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedHeight(24)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        text = TR.t("notif_today") if TR else "TODAY"
        p.setPen(t.c("MUTED"))
        p.setFont(QFont(family(True), 8))
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text)
        p.drawText(QRectF(0, 0, w, self.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.setPen(QPen(t.c("LINE"), 1))
        p.drawLine(QPointF(w + 10, self.height() / 2), QPointF(self.width(), self.height() / 2))
        p.end()


class NotificationDrawer(QWidget):
    cleared = Signal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.progress = 0.0
        self.notes = []
        self.entry_widgets = []
        self.empty = None
        self._clear_anim = None
        self.setFixedWidth(NOTIF_W)
        self.setAutoFillBackground(False)
        body = QVBoxLayout(self)
        body.setContentsMargins(NOTIF_PAD, NOTIF_PAD, NOTIF_PAD, NOTIF_PAD)
        body.setSpacing(0)
        self.header = QWidget(self)
        self.header.setFixedHeight(NOTIF_HEADER)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.bell = QLabel()
        self.bell.setPixmap(icon_pixmap("bell", 18, theme.tokens["MUTED"]))
        self.bell.setFixedSize(20, 22)
        header.addWidget(self.bell)
        self.title = QLabel()
        self.title.setStyleSheet(f"font-size:13px; font-weight:600; color:{theme.tokens['TEXT']};")
        self.title.setText(TR.t("notes_title") if TR else "Notification Center")
        header.addWidget(self.title)
        header.addStretch(1)
        self.clear = ClearAllButton(theme)
        self.clear.clicked.connect(self.clear_all)
        header.addWidget(self.clear)
        body.addWidget(self.header)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.host = QWidget()
        self.host.setStyleSheet("background: transparent;")
        self.entry_layout = QVBoxLayout(self.host)

        self.entry_layout.setContentsMargins(0, 8, 6, 0)
        self.entry_layout.setSpacing(NOTIF_GAP)
        self.scroll.setWidget(self.host)
        body.addWidget(self.scroll, 1)
        self.apply_theme()
        self._rebuild()
        self.hide()

    def _target_height(self) -> int:
        content = NOTIF_PAD * 2 + NOTIF_HEADER + 8
        heights = [entry.height() for entry in self.entry_widgets]
        if heights:
            content += sum(heights) + (len(heights) - 1) * NOTIF_GAP
        return max(NOTIF_MIN_H, min(NOTIF_MAX_H, content))

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; } "
            "QScrollArea > QWidget > QWidget { background: transparent; } "
            f"QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }} "
            f"QScrollBar::handle:vertical {{ background: {t['EDGE']}; min-height: 24px; border-radius: 3px; }} "
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        self.bell.setPixmap(icon_pixmap("bell", 18, t["MUTED"]))
        self.title.setStyleSheet(f"font-size:13px; font-weight:600; color:{t['TEXT']};")
        for entry in self.entry_widgets:
            entry.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        for i, alpha in enumerate((26, 16, 8)):
            shadow = QRectF(3 + i, 4 + i, self.width() - 6 - 2 * i, self.height() - 6 - 2 * i)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(shadow, 16, 16)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("GLASS"))
        p.drawRoundedRect(rect, 16, 16)
        p.end()

    def add_note(self, text: str, kind: str) -> None:
        note = (time.strftime("%H:%M"), str(text), kind)
        self.notes.insert(0, note)
        del self.notes[50:]
        self._rebuild()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_layout_notes"):
            parent._layout_notes()
        if self.isVisible():
            self.update()

    def _rebuild(self) -> None:
        self.entry_widgets = []
        while self.entry_layout.count():
            item = self.entry_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.empty = None
        if self.notes:
            for note in self.notes:
                entry = NotificationEntry(note, self.theme, self.host)
                entry.dismissed.connect(self._dismiss)
                entry.copied.connect(lambda _text: None)
                self.entry_layout.addWidget(entry)
                self.entry_widgets.append(entry)
        else:
            self.empty = QLabel(TR.t("notes_empty") if TR else "Nothing yet - start the loop and events show up here.")
            self.empty.setWordWrap(True)
            self.empty.setAlignment(Qt.AlignCenter)
            self.empty.setStyleSheet(f"color:{self.theme.tokens['MUTED']}; font-size:11px; padding:24px 12px;")
            self.entry_layout.addStretch(1)
            self.entry_layout.addWidget(self.empty)
        self.entry_layout.addStretch(1)
        target = self._target_height()
        self.setFixedHeight(target)
        self.scroll.setFixedHeight(max(0, target - 2 * NOTIF_PAD - NOTIF_HEADER))

        self.scroll.verticalScrollBar().setValue(0)

    def _dismiss(self, note) -> None:
        try:
            self.notes.remove(note)
        except ValueError:
            pass
        self._rebuild()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_layout_notes"):
            parent._layout_notes()

    def clear_all(self) -> None:
        if not self.notes:
            return
        if self._clear_anim is not None:
            self._clear_anim.stop()
        effect = QGraphicsOpacityEffect(self.host)
        self.host.setGraphicsEffect(effect)
        anim = QVariantAnimation(self)
        anim.setDuration(160)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.valueChanged.connect(lambda v: effect.setOpacity(float(v)))
        anim.finished.connect(self._clear_done)
        self._clear_anim = anim
        anim.start()

    def _clear_done(self) -> None:
        self.notes.clear()
        self.host.setGraphicsEffect(None)
        self._clear_anim = None
        self._rebuild()
        self.cleared.emit()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_layout_notes"):
            parent._layout_notes()

    def retranslate(self) -> None:
        self.title.setText(TR.t("notes_title") if TR else "Notification Center")
        self.clear.set_text(
            TR.t("notif_clear") if TR else "CLEAR ALL", TR.t("notif_clear_tip") if TR else "Clear all notifications"
        )
        if self.empty is not None:
            self.empty.setText(TR.t("notes_empty") if TR else "Nothing yet - start the loop and events show up here.")
        for entry in self.entry_widgets:
            entry.retranslate()
        self.update()


NotifPanel = NotificationDrawer


class ConfirmBox(QFrame):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._on_yes = None
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(360, 148)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.label, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.no = QPushButton()
        self.yes = QPushButton()
        for b in (self.no, self.yes):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
        self.no.clicked.connect(self.dismiss)
        self.yes.clicked.connect(self._accept)
        row.addWidget(self.no)
        row.addWidget(self.yes)
        lay.addLayout(row)
        self.hide()

    def ask(self, text: str, on_yes) -> None:
        self._on_yes = on_yes
        self.label.setText(text)
        self.no.setText(TR.t("no") if TR else "No")
        self.yes.setText(TR.t("yes") if TR else "Yes")
        self.apply_theme()
        if self.parent() is not None:
            self.move(max(12, (self.parent().width() - self.width()) // 2), 170)
        self.show()

    def dismiss(self) -> None:
        self._on_yes = None
        self.hide()

    def _accept(self) -> None:
        fn, self._on_yes = self._on_yes, None
        self.hide()
        if fn is not None:
            fn()

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.setStyleSheet(
            f"ConfirmBox {{ background: {t['GLASS']}; border: 1px solid {t['EDGE']}; border-radius: 12px; }} "
            f"QLabel {{ color: {t['TEXT']}; font-size: 12px; }} "
            f"QPushButton {{ background: {t['FIELD']}; color: {t['TEXT']}; border: 1px solid {t['EDGE']}; "
            f"border-radius: 7px; padding: 6px 16px; }} QPushButton:hover {{ background: {t['HOVER']}; }}"
        )
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("GLASS"))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        p.end()


class Shell(QWidget):
    def __init__(self, theme: Theme, settings: Settings, controller=None, reporter=None):
        super().__init__()
        self.theme, self.settings = theme, settings
        self.signals = Signals()
        self.hud = None
        self.overlay = None
        self.remote_service = None
        self.remote_window = None
        self.remote_bridge = None
        self.tunnel = None
        self.remote_host = "0.0.0.0"
        self._taskbar_icons = []
        self._taskbar_sent = False
        self.hud_factory = MiniHud
        self.remote_service_factory = RemoteService
        self.remote_window_factory = RemoteWindow
        self.crop_factory = SnipOverlay
        self.file_log = app_support.FileLogger(
            os.path.join(os.path.dirname(settings.path), "FNauto.log") if os.environ.get("FNAUTO_SETTINGS") else ""
        )
        self._geom_ready = False
        self._auto_stop_fired = False
        self._run_started = None
        global TR
        TR = Translator(settings)
        from controller import MacroController
        from discord_webhook import DiscordReporter

        self.reporter = reporter or DiscordReporter(settings, log=lambda m: self.signals.log_line.emit(m))
        self.controller = controller or MacroController(
            settings,
            on_log=lambda m: self.signals.log_line.emit(m),
            on_state=self._controller_state,
            on_update=self._controller_update,
            on_error=lambda m: self.signals.error.emit(m),
            reporter=self.reporter,
            on_discord=lambda text, kind: self.signals.notify.emit(text, kind),
            on_idle=lambda: self.signals.worker_idle.emit(),
        )
        self.signals.opacity.connect(lambda v: self.setWindowOpacity(v / 100.0))
        self.signals.running_state = False
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        opaque = os.environ.get("FNAUTO_OPAQUE") == "1"
        self.setAttribute(Qt.WA_TranslucentBackground, not opaque)
        if opaque:
            try:
                hwnd = int(self.winId())
                pref = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
            except Exception:
                pass
        self.setWindowIcon(app_icon.icon())
        self.setFixedSize(WIN_W, WIN_H)
        self._restore_window()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(theme.qss())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(PAD, PAD, PAD, PAD)
        outer.setSpacing(0)
        self.title = TitleBar(theme, self)
        outer.addWidget(self.title)
        body = QHBoxLayout()
        body.setContentsMargins(0, GAP, 0, 0)
        body.setSpacing(GAP)
        self.rail = Rail(theme, self)
        body.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.pages = {}
        self.home = HomePage(theme, settings, self.signals)
        self.play = PlayPage(theme, settings, self.signals)
        self.discord = DiscordPage(theme, settings, self.signals, self.reporter)
        self.extras = ExtrasPage(theme, settings, self.signals)
        self.log_page = LogPage(theme, self.signals)
        self.tools = ToolsPage(theme, settings, self.signals)
        self.guide = GuidePage(theme)
        for name, title, page in (
            ("home", "Home", self.home),
            ("play", "Behaviour", self.play),
            ("discord", "Discord", self.discord),
            ("extras", "Extras", self.extras),
            ("log", "Log", self.log_page),
            ("tools", "Tools", self.tools),
            ("guide", "Guide", self.guide),
        ):
            page.setStyleSheet("background: transparent;")
            self.pages[name] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(self.home)
        self.rail.clicked.connect(self.set_page)
        self.rail.quit_clicked.connect(self.close)
        self.title.bell.connect(self.toggle_notes)
        self.title.outside_clicked.connect(self._close_notes)
        self.title.minimise.connect(self.showMinimized)
        self.title.close.connect(self.close)
        self.title.pill.set_running(False)
        self.signals.running.connect(self.title.pill.set_running)
        self.signals.notify.connect(self._notify)
        self.signals.discord_status.connect(self.discord.on_status)
        self.signals.webhook_changed.connect(self._refresh_remote_webhook)
        self.signals.log_line.connect(self._append_log)
        self.log_page.unread_changed.connect(self.rail.set_log_unread)
        self.signals.running.connect(self._status)
        self.signals.start_requested.connect(self._toggle_run)
        self.signals.running.connect(self.home.set_running)
        self.signals.state_changed.connect(self.home.set_state)
        self.signals.error.connect(lambda m: self._notify("error: " + redact(m), "error"))
        self.signals.language_changed.connect(self._language_changed)
        self.signals.hud_requested.connect(self._show_hud)
        self.signals.remote_requested.connect(self._show_remote)
        self.signals.tunnel_status.connect(self._tunnel_status_slot)
        self.signals.tunnel_requested.connect(self._extras_tunnel)
        self.signals.web_remote_requested.connect(self._extras_web_remote)
        self.signals.crop_requested.connect(self._show_crop)
        self.signals.worker_idle.connect(self._worker_idle)
        self.signals.hotkey_stop.connect(self._hotkey_stop)
        self.home.relaunch.clicked.connect(self._relaunch)
        self._hotkey_handle = None
        self._hotkey_cb = lambda: self.signals.hotkey_stop.emit()
        self._sc_next = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._sc_next.setContext(Qt.WindowShortcut)
        self._sc_next.activated.connect(lambda: self._cycle_page(1))
        self._sc_prev = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._sc_prev.setContext(Qt.WindowShortcut)
        self._sc_prev.activated.connect(lambda: self._cycle_page(-1))
        self._page_shortcuts = []
        for i, name in enumerate(("home", "play", "discord", "extras", "log", "tools", "guide"), 1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(lambda n=name: self.set_page(n))
            self._page_shortcuts.append(sc)
        self.settings.changed.connect(self._setting)
        theme.changed.connect(self._theme_changed)
        self.tip = Tooltip(theme)
        self.tip_job = QTimer(self)
        self.tip_job.setSingleShot(True)
        self.tip_job.setInterval(350)
        self.tip_job.timeout.connect(self._show_tip)
        self.tip_name = ""
        self.rail.hovered.connect(self._rail_hover)
        self.scrim = NotifScrim(self)
        self.scrim.clicked.connect(self._close_notes)
        self.notes = NotifPanel(theme, self)
        self.notes.hide()
        self.notes.cleared.connect(self._notes_cleared)
        self.confirm = ConfirmBox(theme, self)
        self.notes_open = False
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(200)
        self.anim.valueChanged.connect(self._notes_step)
        self.anim.finished.connect(self._notes_done)
        self.scrim_anim = QVariantAnimation(self)
        self.scrim_anim.setDuration(140)
        self.scrim_anim.valueChanged.connect(self._scrim_step)
        self.scrim_anim.finished.connect(self._scrim_done)
        self.anim_close = False
        self._sc_esc = QShortcut(QKeySequence("Escape"), self)
        self._sc_esc.setContext(Qt.ApplicationShortcut)
        self._sc_esc.activated.connect(self._close_notes)
        self._sc_esc.setEnabled(False)
        self.card_anims = []
        if settings.first_run and not os.environ.get("FNAUTO_SETTINGS"):
            QTimer.singleShot(180, lambda: self._notify(TR.t("first_run"), "info"))

    def _restore_window(self) -> None:
        try:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            x, y = app_support.window_position(
                self.settings.get("window_x", -1),
                self.settings.get("window_y", -1),
                self.width(),
                self.height(),
                (screen.x(), screen.y(), screen.width(), screen.height()),
            )
            self.move(x, y)
        except Exception:
            pass
        self._geom_ready = True

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if getattr(self, "_geom_ready", False):
            self.settings.set("window_x", int(self.x()))
            self.settings.set("window_y", int(self.y()))

    def resizeEvent(self, _e) -> None:
        self._layout_notes()

    def _notify(self, text: str, kind: str = "info", detail: str = "") -> None:
        text = redact(text)
        note_text = f"{text}\n{detail}" if detail else text
        self.notes.add_note(note_text, _notif_kind(kind))
        if not self.notes_open:
            self.title.unread = min(99, self.title.unread + 1)
            self.title.badge_pop = 1.25
            a = QVariantAnimation(self)
            a.setDuration(220)
            a.setStartValue(1.25)
            a.setEndValue(1.0)
            a.valueChanged.connect(lambda v: (setattr(self.title, "badge_pop", float(v)), self.title.update()))
            a.start()
        self.title.update()

    def _append_log(self, message: str) -> None:
        message = redact(message)
        self.log_page.append_line(message)
        self.file_log.write(message)

    def _notes_cleared(self) -> None:
        self.title.unread = 0
        self.title.update()

    def _layout_notes(self) -> None:
        if not hasattr(self, "stack") or not hasattr(self, "scrim"):
            return
        self.scrim.setGeometry(self.rect())
        self.notes.setGeometry(self._popover_rect(0))

    def _popover_rect(self, offset: int = 0) -> QRect:
        x = WIN_W - 12 - NOTIF_W
        y = PAD + TB + 8 + offset
        return QRect(x, y, NOTIF_W, self.notes.height())

    def _scrim_step(self, v) -> None:
        self.scrim.opacity = float(v)
        eff = self.scrim.graphicsEffect()
        if eff is None:
            eff = QGraphicsOpacityEffect(self.scrim)
            self.scrim.setGraphicsEffect(eff)
        eff.setOpacity(max(0.0, min(1.0, float(v))))

    def _scrim_done(self) -> None:
        if not self.notes_open:
            self.scrim.hide()
            self.scrim.setGraphicsEffect(None)

    def _open_notes(self) -> None:
        if self.notes_open:
            return
        self.notes_open = True
        self._layout_notes()
        self.scrim.show()
        self.scrim.raise_()
        self.notes.show()
        self.notes.raise_()
        self.title.raise_()
        self.title.unread = 0
        self.title.badge_pop = 1.0
        self.title.update()
        self._sc_esc.setEnabled(True)
        self.anim.stop()
        self.anim_close = False
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.OutQuint)
        self.anim.setStartValue(self.notes.progress)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def _close_notes(self) -> None:
        if not self.notes_open and not self.notes.isVisible():
            return
        self.notes_open = False
        self._sc_esc.setEnabled(False)
        self.anim.stop()
        self.anim_close = True
        self.anim.setDuration(120)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self.notes.progress)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _language_changed(self, code: str) -> None:
        global TR
        TR.lang = i18n.norm(code)
        TR.retranslate()
        self.home.retranslate_dynamic()
        self.play.retranslate_dynamic()
        self.discord.retranslate_dynamic()
        self.extras.retranslate_dynamic()
        self.log_page.retranslate_dynamic()
        self.guide.retranslate_dynamic()
        self.tools.retranslate_dynamic()
        if self.remote_window is not None:
            self.remote_window.retranslate()
        self.notes.retranslate()
        self.title.pill._fit()
        name = config.LANGS.get(TR.lang, TR.lang)
        self.language_log = i18n.t(TR.lang, "log_language", name=name)
        self.signals.log_line.emit(self.language_log)
        if self.tip.isVisible():
            self.tip.hide()
        self.setStyleSheet(self.theme.qss())
        for w in (
            self,
            self.title,
            self.rail,
            self.home,
            self.play,
            self.discord,
            self.extras,
            self.log_page,
            self.guide,
            self.tools,
            self.notes,
        ):
            w.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.setFocus()
        QTimer.singleShot(0, self.clearFocus)
        QTimer.singleShot(0, self._send_taskbar_icon)
        QTimer.singleShot(0, lambda: self._apply_topmost(bool(self.settings.get("topmost"))))

    def _send_taskbar_icon(self) -> None:
        if self._taskbar_sent:
            return
        self._taskbar_sent = True
        try:
            if QGuiApplication.platformName() == "offscreen" or os.name != "nt":
                return
            self._taskbar_icons = app_support.apply_taskbar_icon(int(self.winId()))
        except Exception:
            self._taskbar_icons = []

    def mousePressEvent(self, e) -> None:
        self.clearFocus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape and self.notes_open:
            self._close_notes()
            e.accept()
            return
        super().keyPressEvent(e)

    def _loop_mode(self) -> str:
        return str(self.settings.get("mode", "A"))

    def _loop_start_detail(self) -> str:
        return TR.t("notif_mode_detail", mode=self._loop_mode()) if TR else f"Mode {self._loop_mode()}"

    def _loop_stop_detail(self) -> str:
        parts = [self._loop_start_detail()]
        laps = self.home.values["laps"].text().strip()
        if laps and laps != "0":
            parts.append(TR.t("notif_laps_detail", n=laps) if TR else f"{laps} laps")
        if self._run_started is not None:
            seconds = max(0, int(time.monotonic() - self._run_started))
            minutes, seconds = divmod(seconds, 60)
            parts.append(TR.t("notif_duration_detail", m=minutes, s=seconds) if TR else f"{minutes}m {seconds:02d}s")
        return " · ".join(parts)

    def _toggle_run(self) -> None:
        if self.controller.running():
            self._stop_run()
        elif self.controller.stopping():
            self.home.set_stopping()
        elif self.controller.start():
            self._auto_stop_fired = False
            self._run_started = time.monotonic()
            self.signals.running.emit(True)
            self._notify(
                TR.t("notif_loop_started") if TR else "Loop started",
                "success",
                detail=self._loop_start_detail(),
            )

    def _stop_run(self) -> None:
        self.home.set_stopping()
        self.controller.stop()
        self._notify(
            TR.t("notif_loop_stopped") if TR else "Loop stopped",
            "info",
            detail=self._loop_stop_detail(),
        )
        self._run_started = None

    def _worker_idle(self) -> None:
        self.signals.running.emit(False)

    def _hotkey_stop(self) -> None:
        if self.controller.running():
            self._stop_run()

    def _cycle_page(self, step: int) -> None:
        names = list(self.pages)
        cur = self.stack.currentWidget()
        idx = next((i for i, n in enumerate(names) if self.pages[n] is cur), 0)
        self.set_page(names[(idx + step) % len(names)])

    def install_hotkey(self) -> bool:
        if self._hotkey_handle is not None:
            return True
        try:
            import keyboard

            self._hotkey_handle = keyboard.add_hotkey("f8", self._hotkey_cb)
            return True
        except Exception as e:
            self._notify(f"F8 unavailable: {e}", "error")
            return False

    def uninstall_hotkey(self) -> None:
        if self._hotkey_handle is None:
            return
        try:
            import keyboard

            keyboard.remove_hotkey(self._hotkey_handle)
        except Exception:
            pass
        self._hotkey_handle = None

    def _apply_topmost(self, enabled: bool) -> None:
        try:
            set_window_topmost(int(self.winId()), bool(enabled))
        except Exception:
            pass

    def _relaunch(self) -> None:
        self.confirm.ask(TR.t("relaunch_ask"), self._do_relaunch)

    def _do_relaunch(self) -> None:
        fn = getattr(self, "relaunch_fn", None)
        if fn is None:
            import relauncher

            fn = relauncher.manual_relaunch
        self._notify("Relaunching game…", "info")
        self.relaunch_thread = fn(self.settings)

    def closeEvent(self, e) -> None:
        if self.hud is not None:
            self.hud.close()
            self.hud = None
        if self.remote_window is not None:
            self.remote_window.close()
            self.remote_window = None
        if self.remote_service is not None:
            self.remote_service.stop(quiet=True)
            self.remote_service = None
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.stop()
        w = self.controller.worker
        if w is not None and w.is_alive():
            self.controller.stop()
            self.controller.join(3.0)
        try:
            self.reporter.flush(3.0)
        except Exception:
            pass
        self.uninstall_hotkey()
        try:
            self.settings.save()
        except Exception:
            pass
        super().closeEvent(e)

    def _status(self, run: bool) -> None:
        self.signals.status.emit({"state": "RUNNING" if run else "IDLE"})

    def _controller_state(self, state: str, score: float, loops: int) -> None:
        self.signals.state_changed.emit(state, score, loops)
        self.signals.hud_status.emit({"state": state, "score": score, "loops": loops})
        self._check_auto_stop(loops)

    def _controller_update(self, data: dict) -> None:
        data = dict(data)
        self.signals.state_changed.emit(
            str(data.get("state", "IDLE")), float(data.get("score", 0.0)), int(data.get("loops", 0))
        )
        self.signals.hud_status.emit(data)
        self._check_auto_stop(int(data.get("loops", 0) or 0))

    def _check_auto_stop(self, loops: int) -> None:
        limit = int(self.settings.get("auto_stop_laps", 0) or 0)
        if not limit or loops < limit or self._auto_stop_fired or not self.controller.running():
            return
        self._auto_stop_fired = True
        msg = TR.t("log_auto_stop", n=limit) if TR else f"auto-stop after {limit} laps"
        self.signals.log_line.emit(msg)
        self._notify(msg, "info")
        self._stop_run()

    def _show_hud(self) -> None:
        if self.hud is not None:
            self.hud.show()
            return
        try:
            self.hud = self.hud_factory(self.theme, self.settings, self._toggle_run, self._hide_hud, self._hud_moved)
            self.signals.state_changed.connect(self.hud.on_state)
            self.signals.hud_status.connect(self.hud.on_status)
            self.signals.running.connect(self.hud.set_running)
            self.settings.changed.connect(self.hud.on_setting)
            self.theme.changed.connect(self.hud.apply_theme)
            self.hud.set_running(bool(self.signals.running_state))
            self.hud.on_status(dict(self.controller.status))
            self.hud.show()
            self.hide()
        except Exception as e:
            self.hud = None
            self._notify(f"HUD: {type(e).__name__}: {e}", "error")

    def _hide_hud(self) -> None:
        hud, self.hud = self.hud, None
        if hud is not None:
            hud.close()
            hud.deleteLater()
        self.show()

    def _hud_moved(self, x: int, y: int) -> None:
        self.settings.set("hud_x", int(x))
        self.settings.set("hud_y", int(y))

    def start_remote_service(self) -> bool:
        try:
            if self.remote_service is None:
                self.remote_bridge = RemoteBridge(
                    self.settings,
                    self.controller,
                    log=lambda m: self.signals.log_line.emit(m),
                    start=lambda: self.signals.start_requested.emit(),
                    stop=self._stop_run,
                    on_mode=lambda v: self.settings.set("mode", v),
                    on_power=self._remote_power,
                )
                self.remote_service = self.remote_service_factory(
                    self.settings,
                    self.remote_bridge,
                    host=self.remote_host,
                    log=lambda m: self.signals.log_line.emit(m),
                )
            if self.remote_service.running:
                return True
            if not self.remote_service.start():
                self._notify(TR.t("rm_failed") if TR else i18n.t("en", "rm_failed"), "error")
                return False
            return True
        except Exception as e:
            self._notify(f"remote: {type(e).__name__}: {e}", "error")
            return False

    def _show_remote(self) -> None:
        if self.remote_window is not None:
            self.remote_window.show()
            self.remote_window.center_on_parent()
            return
        if not self.start_remote_service():
            return
        try:
            if self.tunnel is None:
                import tunnel as tunnel_mod

                self.tunnel = tunnel_mod.Tunnel(on_status=lambda s, d="": self.signals.tunnel_status.emit(s, d))
            self.remote_window = self.remote_window_factory(
                self.theme,
                self.settings,
                self.remote_service,
                on_close=self._remote_closed,
                on_tunnel=self._toggle_tunnel,
                on_send_url=self._send_remote_url,
                parent=self,
            )
            self.theme.changed.connect(self.remote_window.apply_theme)
            self.remote_window.refresh_webhook()
            self.remote_window.show()
            if self.settings.get("web_remote_tunnel", False):
                self._start_tunnel(False)
        except Exception as e:
            self._notify(f"remote: {type(e).__name__}: {e}", "error")

    def _remote_closed(self) -> None:
        self.remote_window = None
        if self.tunnel is not None:
            self.tunnel.stop()
            self.tunnel = None
        if self.remote_service is not None:
            self.remote_service.set_public(False)

    def _toggle_tunnel(self) -> None:
        if self.tunnel is None or self.remote_service is None:
            return
        if self.tunnel.running:
            self.tunnel.stop()
            self.settings.set("web_remote_tunnel", False)
            if self.remote_service is not None:
                self.remote_service.set_public(False)
            if self.remote_window is not None:
                self.remote_window.set_tunnel("off")
            return
        import tunnel as tunnel_mod

        folder = tunnel_mod.bin_dir()
        if tunnel_mod.find_cloudflared() is None:
            self.confirm.ask(TR.t("rm_dl_confirm", folder=folder), lambda: self._start_tunnel(True))
        else:
            self._start_tunnel(False)

    def _extras_tunnel(self, on: bool) -> None:
        if on:
            if self.remote_window is None:
                self._show_remote()
            if self.tunnel is not None and not self.tunnel.running:
                self._toggle_tunnel()
        elif self.tunnel is not None and self.tunnel.running:
            self.tunnel.stop()
            self.settings.set("web_remote_tunnel", False)
            if self.remote_service is not None:
                self.remote_service.set_public(False)
            if self.remote_window is not None:
                self.remote_window.set_tunnel("off")

    def _extras_web_remote(self, on: bool) -> None:
        if on:
            self._show_remote()
        else:
            if self.remote_window is not None:
                self.remote_window.close()
            if self.remote_service is not None:
                self.remote_service.stop(quiet=True)
                self.remote_service = None
            self.settings.set("web_remote_enabled", False)

    def _start_tunnel(self, allow_download: bool) -> None:
        if self.tunnel is None or self.remote_service is None:
            return
        self.settings.set("web_remote_tunnel", True)
        self.tunnel.start(self.remote_service.port, allow_download=allow_download)

    def _tunnel_status_slot(self, status: str, detail: str = "") -> None:
        if self.remote_window is not None:
            self.remote_window.set_tunnel(status, detail)
        if status == "ready":
            self.settings.set("web_remote_tunnel", True)
            if self.remote_service is not None:
                self.remote_service.set_public(True)
            self._notify(TR.t("rm_t_ready"), "success")
        elif status in ("failed", "stopped"):
            self.settings.set("web_remote_tunnel", False)
            if self.remote_service is not None:
                self.remote_service.set_public(False)
            if status == "failed":
                self._notify(TR.t("rm_t_failed", reason=detail), "error")

    def _send_remote_url(self) -> None:
        if self.remote_window is None:
            return
        if not self.reporter.configured:
            self._notify(TR.t("dm_s_no_url") if TR else i18n.t("en", "dm_s_no_url"), "error")
            return
        url = self.remote_window.url.text()
        self.reporter.send_remote_url(url, callback=lambda st: self.signals.discord_status.emit(st))

    def _refresh_remote_webhook(self) -> None:
        if self.remote_window is not None:
            self.remote_window.refresh_webhook()

    def _remote_power(self, name: str) -> bool:
        import power_tools

        if name == "relaunch":
            self._do_relaunch()
            return True
        if name == "sleep":
            return power_tools.sleep_pc()
        if name == "kill":
            return power_tools.kill_game()
        return False

    def _show_crop(self, key: str) -> None:
        if self.overlay is not None:
            return
        lang = TR.lang if TR else "en"

        def done(path, error=None) -> None:
            self.overlay = None
            self.show()
            if path:
                msg = TR.t("log_saved", path=path) if TR else i18n.t("en", "log_saved", path=path)
            elif error:
                msg = str(error)
            else:
                msg = TR.t("log_cancelled") if TR else i18n.t("en", "log_cancelled")
            self.signals.log_line.emit(msg)

        try:
            overlay = self.crop_factory(key, lang, done)
            self.overlay = overlay
            self.hide()
            if hasattr(overlay, "showFullScreen"):
                overlay.showFullScreen()
            else:
                overlay.show()
        except Exception as e:
            self.overlay = None
            self.show()
            msg = TR.t("log_capture_error", error=e) if TR else i18n.t("en", "log_capture_error", error=e)
            self.signals.log_line.emit(msg)

    def _setting(self, key, value) -> None:
        if key == "ui_theme":
            self.theme.set(str(value))
        elif key == "topmost":
            self._apply_topmost(bool(value))
        elif key == "discord_webhook_url":
            self._refresh_remote_webhook()

    def _theme_changed(self, _name) -> None:
        t0 = time.perf_counter()
        self.setStyleSheet(self.theme.qss())
        for page in (self.extras, self.log_page, self.guide):
            page.apply_theme()
        if self.remote_window is not None:
            self.remote_window.apply_theme()
        self.confirm.apply_theme()
        self.notes.apply_theme()
        for combo in self.findChildren(ChevronCombo):
            combo.apply_theme()
        for w in (self.title, self.rail, self.home, self.tools):
            w.update()
        for page in self.pages.values():
            page.update()
        self.theme_ms = (time.perf_counter() - t0) * 1000

    def _rail_hover(self, name: str) -> None:
        self.tip_name = name
        if not name:
            self.tip.hide()
            self.tip_job.stop()
            return
        self.tip_job.start()

    def _show_tip(self) -> None:
        name = self.tip_name
        if not name:
            return
        key = {
            "home": "nav_home",
            "play": "nav_play",
            "discord": "nav_discord",
            "extras": "nav_extras",
            "log": "nav_log",
            "tools": "nav_tools",
            "guide": "nav_guide",
            "quit": "nav_quit",
        }.get(name, name)
        label = TR.t(key) if TR else name
        c = self.rail.icon_center(name)
        gp = self.rail.mapToGlobal(QPoint(c.x() + 26, c.y() - 10))
        self.tip.show_for(label, gp)
        self.tip_ok = self.tip.width() >= QFontMetrics(self.tip.label.font()).horizontalAdvance(label) + 18

    def set_page(self, name: str, animate: bool = True) -> None:
        if name not in self.pages:
            return
        if self.notes_open and self.pages[name] is not self.stack.currentWidget():
            self._close_notes()
        self.t0 = time.perf_counter()
        page = self.pages[name]
        self.stack.setCurrentWidget(page)
        self.rail.set_active(name)
        self.log_page.set_active(name == "log")
        self.card_anims = []
        if animate and not REDUCE_MOTION:
            eff = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", self)
            a.setDuration(160)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.finished.connect(lambda: page.setGraphicsEffect(None))
            a.start()
            self.card_anims.append(a)
            for i, card in enumerate(page.cards[:5]):
                e2 = QGraphicsOpacityEffect(card)
                card.setGraphicsEffect(e2)
                a2 = QPropertyAnimation(e2, b"opacity", self)
                a2.setDuration(160)
                a2.setStartValue(0.0)
                a2.setEndValue(1.0)
                a2.setEasingCurve(QEasingCurve.OutCubic)
                QTimer.singleShot(i * 40, lambda a2=a2: a2.start())
                a2.finished.connect(lambda c=card: c.setGraphicsEffect(None))
                self.card_anims.append(a2)

    def toggle_notes(self) -> None:
        if self.notes_open:
            self._close_notes()
        else:
            self._open_notes()

    def _notes_step(self, v) -> None:
        self.notes.progress = float(v)
        self.notes.setGeometry(self._popover_rect(round(8 * (1.0 - float(v)))))
        eff = self.notes.graphicsEffect()
        if eff is None:
            eff = QGraphicsOpacityEffect(self.notes)
            self.notes.setGraphicsEffect(eff)
        eff.setOpacity(max(0.0, min(1.0, float(v))))

    def _notes_done(self) -> None:
        if self.anim_close:
            self.notes.hide()
            self.notes.setGraphicsEffect(None)
            self.scrim.hide()
            self.scrim.setGraphicsEffect(None)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(t.c("EDGE"), 1))
        p.setBrush(t.c("BG0"))
        p.drawRoundedRect(rect, RADIUS, RADIUS)
        p.setClipPath(rounded_path(rect, RADIUS))
        step = 36
        p.setPen(QPen(t.c("EDGE_SOFT", 28), 1))
        for x in range(0, self.width(), step):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)
        p.end()


HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010


def set_window_topmost(hwnd: int, enabled: bool) -> bool:
    fn = ctypes.windll.user32.SetWindowPos
    try:
        fn.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        fn.restype = ctypes.c_bool
    except Exception:
        pass
    return bool(
        fn(int(hwnd), HWND_TOPMOST if enabled else HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    )


def build_app(argv=None):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FNauto.FNauto.1")
    except Exception:
        pass
    app = QApplication(argv or sys.argv)
    app.setWindowIcon(app_icon.icon())
    load_fonts()
    theme = Theme()
    settings = Settings()
    shell = Shell(theme, settings)
    return app, theme, settings, shell


def main() -> int:
    def arg_value(flag: str) -> str:
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
                return sys.argv[i + 1]
        return ""

    diag_path = arg_value("--diagnose")
    if diag_path:
        import diagnose

        diagnose.run(diag_path)
        return 0
    probe_path = arg_value("--probe-remote")
    selftest_path = arg_value("--selftest")
    if selftest_path:
        app_support.selftest_report(selftest_path)
        with open(selftest_path, "a", encoding="utf-8") as f:
            f.write("exception hook: ok (headless selftest)\n")
        return 0
    info = [a for a in sys.argv if a.startswith("--settings-info=")]
    if info:
        path = settings_path()
        try:
            data = json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            data = {}
        with open(info[0].split("=", 1)[1], "w", encoding="utf-8") as f:
            json.dump({"path": path, "lang": data.get("lang"), "ui_opacity": data.get("ui_opacity")}, f)
        return 0
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FNauto.FNauto.1")
    except Exception:
        pass
    selftest = "--selftest" in sys.argv
    probe = bool(probe_path)
    if selftest and not os.environ.get("FNAUTO_SETTINGS"):
        os.environ["FNAUTO_SETTINGS"] = os.path.join(tempfile.mkdtemp(prefix="fnauto-selftest-"), config.SETTINGS_FILE)
    guard = app_support.InstanceGuard("FNauto.FNauto.1")
    if not selftest and not probe and not guard.acquire():
        return 0
    app, theme, settings, shell = build_app(
        [a for a in sys.argv if a not in ("--selftest", "--probe-remote") and a != probe_path]
    )

    hook_events = []

    def _crash_notice(message: str) -> None:
        message = redact(message)
        hook_events.append(message)
        shell.signals.log_line.emit(message)
        shell.signals.notify.emit(message, "error")

    app_support.install_excepthook(shell.file_log, _crash_notice)
    if not selftest and not probe:
        app_support.ghost_recovery()
    shell.show()
    if not selftest:
        if settings.get("phone_remote_autostart", False):
            QTimer.singleShot(0, shell.start_remote_service)
    if not selftest and not probe:
        shell.install_hotkey()
        from tray import Tray

        shell.tray = Tray(shell)
        shell.tray.start()
        if UPDATE_REPO and settings.get("auto_update_check", False):
            QTimer.singleShot(900, shell.tools.update_service.check)
    if selftest:
        QTimer.singleShot(3000, app.quit)
    if probe:

        def _probe_report():
            import socket

            port = int(settings.get("web_remote_port", 8765) or 8765)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.25)
            try:
                listening = sock.connect_ex(("127.0.0.1", port)) == 0
            except OSError:
                listening = False
            finally:
                sock.close()
            visible = [type(w).__name__ for w in app.topLevelWidgets() if w.isVisible()]
            data = {
                "visible_windows": visible,
                "remote_window": shell.remote_window is not None,
                "remote_service": shell.remote_service is not None and shell.remote_service.running,
                "remote_threads": [t.name for t in threading.enumerate() if t.name == "FNauto-web-remote"],
                "port": port,
                "port_open": listening,
                "autostart_setting": bool(settings.get("phone_remote_autostart", False)),
                "old_setting": bool(settings.get("web_remote_enabled", False)),
            }
            try:
                with open(probe_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
            except OSError:
                pass
            app.quit()

        QTimer.singleShot(3000, _probe_report)
    try:
        rc = app.exec()
        if selftest:
            status = "ok" if not hook_events else f"FAIL {len(hook_events)}: {hook_events[0][:180]}"
            try:
                with open(selftest_path, "a", encoding="utf-8") as f:
                    f.write(f"exception hook: {status}\n")
            except OSError:
                pass
            if hook_events:
                return 1
        return rc
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
