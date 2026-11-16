import ctypes
import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from i18n_hud import STATE_SHORT

WIDTH, HEIGHT = 420, 34
ALPHA = 0.96
WAIT_STATES = ("A:LOADING", "IN_MATCH", "B:WAITING", "B:LOADING")


def indicator(running: bool, stuck: bool, state: str) -> str:
    if stuck:
        return "stuck"
    if not running:
        return "stop"
    return "wait" if state in WAIT_STATES else "run"


def short_state(state: str) -> str:
    return STATE_SHORT.get(state, str(state).upper()[:8])


def eta_seconds(status: dict, now: Optional[float] = None) -> Optional[int]:
    eta = status.get("eta")
    if eta is None:
        return None
    t = status.get("eta_t")
    current = time.monotonic() if now is None else now
    left = float(eta) - (current - float(t)) if t is not None else float(eta)
    return max(0, int(round(left)))


def clock_text(seconds: Optional[int]) -> str:
    if seconds is None:
        return "--:--"
    value = min(int(seconds), 5999)
    return f"{value // 60:02d}:{value % 60:02d}"


def view_of(running: bool, mode: str, lang: str, status: dict, now: Optional[float] = None) -> dict:
    state = str(status.get("state", "IDLE"))
    stuck = bool(status.get("stuck", False)) and running
    return {
        "running": bool(running),
        "stuck": stuck,
        "state": state,
        "mode": mode,
        "lang": lang,
        "loops": int(status.get("loops", 0) or 0),
        "claims": int(status.get("claims", 0) or 0),
        "eta": eta_seconds(status, now) if running else None,
        "ind": indicator(running, stuck, state),
    }


def layout_parts(view: dict, colors: dict) -> tuple:
    return (
        colors[view["ind"]],
        short_state(view["state"]),
        f"{view['loops']} LAPS",
        f"{view['claims']:02d} CLM",
        clock_text(view["eta"]),
    )


def clamp_pos(x: int, y: int, w: int, h: int, vx: int, vy: int, vw: int, vh: int) -> tuple:
    return max(vx, min(int(x), vx + vw - w)), max(vy, min(int(y), vy + vh - h))


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(ca, cb))


class MiniHud(QWidget):
    def __init__(self, theme, settings, on_toggle=None, on_back=None, on_move=None, parent=None):
        super().__init__(parent)
        self.theme, self.settings = theme, settings
        self._toggle = on_toggle or (lambda: None)
        self._back = on_back or (lambda: None)
        self._move = on_move or (lambda _x, _y: None)
        self.running = False
        self.status = {"state": "IDLE", "loops": 0, "claims": 0}
        self._drag = None
        self._pressed = None
        self._hover = None
        self.last_parts = None
        self.last_view = None
        self.setWindowTitle("FNauto HUD")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setWindowOpacity(ALPHA)
        screen = QGuiApplication.primaryScreen()
        self.k = max(1.0, float(screen.logicalDotsPerInch()) / 96.0) if screen else 1.0
        self.w, self.h = int(round(WIDTH * self.k)), int(round(HEIGHT * self.k))
        self.setFixedSize(self.w, self.h)
        self._place()
        self._refresh()

    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        x, y = int(self.settings.get("hud_x", -1)), int(self.settings.get("hud_y", -1))
        if (x, y) == (-1, -1):
            x, y = rect.x() + rect.width() - self.w - 24, rect.y() + 24
        x, y = clamp_pos(x, y, self.w, self.h, rect.x(), rect.y(), rect.width(), rect.height())
        self.move(x, y)

    def _apply_noactivate(self) -> None:
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            put = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            style = get(hwnd, -20)
            put(hwnd, -20, style | 0x08000000 | 0x00000080)
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_noactivate()

    def _colours(self) -> dict:
        t = self.theme.tokens
        return {
            "run": t["GOOD"],
            "wait": "#F59E0B",
            "stop": t["MUTED"],
            "stuck": t["DANGER"],
            "bg": t["BG0"],
            "border": t["EDGE"],
            "fg": t["TEXT"],
            "dim": t["MUTED"],
            "hover": t["HOVER"],
        }

    def _refresh(self) -> None:
        status = dict(self.status)
        if bool(self.settings.get("rescue_listening", False)):
            status.setdefault("stuck", True)
        view = view_of(self.running, str(self.settings.get("mode", "A")), str(self.settings.get("lang", "en")), status)
        self.last_view = view
        self.last_parts = layout_parts(view, self._colours())
        self.update()

    def on_status(self, status: dict) -> None:
        if isinstance(status, dict):
            self.status.update(status)
        self._refresh()

    def on_state(self, state: str, _score: float, loops: int) -> None:
        self.status["state"] = str(state)
        self.status["loops"] = int(loops)
        self._refresh()

    def set_running(self, running: bool) -> None:
        self.running = bool(running)
        if not self.running:
            self.status["state"] = "IDLE"
        self._refresh()

    def on_setting(self, _key: str, _value) -> None:
        self._refresh()

    def apply_theme(self, *_args) -> None:
        self.update()

    def _font(self, bold: bool = False) -> QFont:
        font = QFont("Consolas", 9)
        font.setBold(bold)
        font.setPixelSize(max(9, int(round(12 * self.k))))
        return font

    def _button_rects(self, _painter: QPainter) -> dict:
        fm = QFontMetrics(self._font(True))
        pad = int(7 * self.k)
        bh = self.h - int(12 * self.k)
        out = {}
        right = self.w - int(6 * self.k)
        for name, text in (("back", "[EXPAND]"), ("toggle", "[STOP]" if self.running else "[RUN]")):
            bw = fm.horizontalAdvance(text) + 2 * pad
            out[name] = (QRect(right - bw, (self.h - bh) // 2, bw, bh), text)
            right -= bw + int(4 * self.k)
        return out

    def paintEvent(self, _event) -> None:
        c = self._colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.w, self.h
        p.fillRect(QRectF(0, 0, w, h), QColor(c["bg"]))
        p.setPen(QPen(QColor(c["border"]), 1))
        p.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
        view = self.last_view or view_of(self.running, "A", "en", self.status)
        colour = c[view["ind"]]
        cy = h // 2
        r = max(3.0, 4.0 * self.k)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_mix(colour, c["bg"], 0.6)))
        p.drawEllipse(QRectF(14 * self.k - r - 1, cy - r - 1, 2 * r + 2, 2 * r + 2))
        p.setBrush(QColor(colour))
        p.drawEllipse(QRectF(14 * self.k - r, cy - r, 2 * r, 2 * r))
        p.setFont(self._font())
        fm = QFontMetrics(self._font())
        x = 30 * self.k
        gap = fm.horizontalAdvance("  ")
        parts = layout_parts(view, c)
        for text, fill in zip(parts[1:], (c["fg"], c["fg"], c["fg"], colour if view["running"] else c["dim"])):
            p.setPen(QColor(fill))
            p.drawText(QPoint(int(x), int(cy + fm.ascent() / 2 - 1)), text)
            x += fm.horizontalAdvance(text) + gap
        p.setFont(self._font(True))
        for name, (rect, text) in self._button_rects(p).items():
            fill = c["hover"] if self._hover == name else c["bg"]
            p.fillRect(rect, QColor(fill))
            p.setPen(QColor(c["fg"]))
            p.drawText(rect, Qt.AlignCenter, text)
        p.end()

    def _hit(self, pos: QPoint):
        for name, (rect, _text) in self._button_rects(None).items():
            if rect.contains(pos):
                return name
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        name = self._hit(pos)
        if name:
            self._pressed = name
            return
        self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            return
        name = self._hit(event.position().toPoint())
        if name != self._hover:
            self._hover = name
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        name = self._pressed
        self._pressed = None
        if name is not None and self._hit(event.position().toPoint()) == name:
            if name == "toggle":
                self._toggle()
            else:
                self._back()
            return
        if self._drag is not None:
            self._drag = None
            self._apply_noactivate()
            self._move(self.x(), self.y())

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def closeEvent(self, event) -> None:
        self._move(self.x(), self.y())
        super().closeEvent(event)
