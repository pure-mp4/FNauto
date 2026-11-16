from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

import app_icon
import i18n
import qr
from discord_webhook import valid_webhook


class QRPanel(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.matrix = []
        self.setFixedSize(236, 236)

    def set_url(self, url: str) -> bool:
        try:
            self.matrix = qr.make_matrix(url)
        except Exception:
            self.matrix = []
        self.update()
        return bool(self.matrix)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self.matrix:
            p.end()
            return
        n = len(self.matrix)
        quiet = 3
        cell = max(1, self.width() // (n + 2 * quiet))
        off = (self.width() - n * cell) // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.theme.tokens["BG0"]))
        for y, row in enumerate(self.matrix):
            for x, dark in enumerate(row):
                if dark:
                    p.drawRect(off + x * cell, off + y * cell, cell, cell)
        p.end()


class ElidedUrlField(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_url = ""
        self.setReadOnly(True)
        self.setCursorPosition(0)

    def set_url(self, url: str) -> None:
        self.full_url = str(url or "")
        self.setToolTip(self.full_url)
        self._apply_elision()

    def text(self) -> str:

        return self.full_url

    def _apply_elision(self) -> None:
        fm = QFontMetrics(self.font())
        width = max(1, self.width() - 18)
        super().setText(fm.elidedText(self.full_url, Qt.ElideMiddle, width))
        self.setCursorPosition(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()


class RemoteTitleBar(QWidget):
    close_clicked = None

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedHeight(34)
        self.setCursor(Qt.OpenHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.mark = QLabel(self)
        self.mark.setPixmap(app_icon.pixmap(18))
        self.mark.setFixedSize(18, 18)
        row.addWidget(self.mark, 0, Qt.AlignVCenter)
        self.label = QLabel("FNauto REMOTE", self)
        self.label.setObjectName("RemoteTitle")
        row.addWidget(self.label, 1)
        self.close_button = QPushButton("\u00d7", self)
        self.close_button.setObjectName("RemoteClose")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setFixedSize(28, 28)
        row.addWidget(self.close_button, 0, Qt.AlignVCenter)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                try:
                    handle.startSystemMove()
                except Exception:
                    pass
        super().mousePressEvent(event)


class RemoteWindow(QWidget):
    def __init__(self, theme, settings, service, on_close=None, parent=None, on_tunnel=None, on_send_url=None):
        super().__init__(parent)
        self.theme, self.settings, self.service = theme, settings, service
        self.on_close = on_close or (lambda: None)
        self.on_tunnel = on_tunnel or (lambda: None)
        self.on_send_url = on_send_url or (lambda: None)
        self.url_override = ""
        self._tunnel_on = False
        self._centered = False
        self.setWindowTitle(i18n.t(str(settings.get("lang", "en")), "rm_title"))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowModality(Qt.NonModal)
        self.setFixedWidth(440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("RemoteCard")
        outer.addWidget(self.card)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(18, 12, 18, 16)
        lay.setSpacing(9)
        self.title = RemoteTitleBar(theme, self)
        self.title.close_button.clicked.connect(self.close)
        lay.addWidget(self.title)
        self.qr = QRPanel(theme)
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.scan = QLabel()
        self.scan.setWordWrap(True)
        lay.addWidget(self.scan)
        url_row = QHBoxLayout()
        self.url = ElidedUrlField()
        self.copy_button = QPushButton("COPY")
        self.copy_button.clicked.connect(self.copy)
        url_row.addWidget(self.url, 1)
        url_row.addWidget(self.copy_button)
        lay.addLayout(url_row)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        lay.addWidget(self.warn)
        self.tunnel_label = QLabel()
        self.tunnel_label.setWordWrap(True)
        lay.addWidget(self.tunnel_label)
        self.send_button = QPushButton("SEND URL TO DISCORD")
        self.send_button.clicked.connect(self.on_send_url)
        lay.addWidget(self.send_button)
        self.send_warning = QLabel()
        self.send_warning.setWordWrap(True)
        lay.addWidget(self.send_warning)
        bottom = QHBoxLayout()
        self.tunnel_button = QPushButton("TUNNEL")
        self.tunnel_button.clicked.connect(self.on_tunnel)
        bottom.addWidget(self.tunnel_button)
        bottom.addStretch(1)
        self.stop_button = QPushButton("STOP REMOTE")
        self.stop_button.clicked.connect(self.stop_remote)
        bottom.addWidget(self.stop_button)
        lay.addLayout(bottom)
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.setInterval(1200)
        self._copy_timer.timeout.connect(self._reset_copy)
        self.apply_theme()
        self.refresh()
        self.adjustSize()

    def _lang(self) -> str:
        return i18n.norm(str(self.settings.get("lang", "en")))

    def _fit_button(self, button: QPushButton) -> None:
        fm = QFontMetrics(button.font())

        button.setMinimumWidth(fm.horizontalAdvance(button.text()) + 32)
        button.setFixedHeight(max(30, fm.height() + 16))

    def _fit_buttons(self) -> None:
        for button in (self.copy_button, self.send_button, self.tunnel_button, self.stop_button):
            self._fit_button(button)

    def center_on_parent(self) -> None:
        target = self.parentWidget()
        if target is not None and target.isVisible():
            area = target.frameGeometry()
        else:
            screen = self.screen()
            area = screen.availableGeometry() if screen is not None else None
        if area is None:
            return
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            self.center_on_parent()

    def refresh(self) -> None:
        url = self.url_override or self.service.url()
        self.url.set_url(url)
        self.qr.set_url(url)
        self.scan.setText(i18n.t(self._lang(), "rm_scan"))
        self.warn.setText(i18n.t(self._lang(), "rm_warn"))
        self.retranslate()

    def set_tunnel(self, status: str, detail: str = "") -> None:
        lang = self._lang()
        if status == "ready" and detail:
            self.url_override = detail
            self._tunnel_on = True
            self.tunnel_label.setText(i18n.t(lang, "rm_wan_warn"))
        elif status in ("off", "stopped"):
            self.url_override = ""
            self._tunnel_on = False
            self.tunnel_label.setText(i18n.t(lang, "rm_t_off"))
        else:
            self._tunnel_on = False
            key = {"downloading": "rm_t_downloading", "starting": "rm_t_starting"}.get(status, "rm_t_failed")
            self.tunnel_label.setText(i18n.t(lang, key, reason=detail) if status == "failed" else i18n.t(lang, key))
        self.refresh()

    def refresh_webhook(self) -> None:
        lang = self._lang()
        enabled = valid_webhook(str(self.settings.get("discord_webhook_url", "") or ""))
        self.send_button.setEnabled(enabled)
        self.send_button.setToolTip("" if enabled else i18n.t(lang, "rm_webhook_none"))
        self.send_warning.setText(i18n.t(lang, "rm_token_warn"))

    def retranslate(self) -> None:
        lang = self._lang()
        self.setWindowTitle(i18n.t(lang, "rm_title"))
        self.scan.setText(i18n.t(lang, "rm_scan"))
        self.warn.setText(i18n.t(lang, "rm_warn"))
        self.send_button.setText(i18n.t(lang, "rm_send_url"))
        self.refresh_webhook()
        self.stop_button.setText(i18n.t(lang, "rm_stop"))
        self.copy_button.setText(i18n.t(lang, "rm_copy"))
        self.tunnel_button.setText(i18n.t(lang, "rm_tunnel_off" if self._tunnel_on else "rm_tunnel"))
        self._fit_buttons()

    def _reset_copy(self) -> None:
        self.copy_button.setText(i18n.t(self._lang(), "rm_copy"))
        self._fit_button(self.copy_button)

    def copy(self) -> None:
        QApplication.clipboard().setText(self.url.text())
        self.copy_button.setText(i18n.t(self._lang(), "rm_copied"))
        self._fit_button(self.copy_button)
        self._copy_timer.start()

    def stop_remote(self) -> None:
        self.service.stop()
        self.close()

    def closeEvent(self, event) -> None:
        self.on_close()
        super().closeEvent(event)

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.setStyleSheet(
            f"QFrame#RemoteCard {{ background: {t['GLASS']}; border: 1px solid {t['EDGE']}; "
            f"border-radius: 16px; }} QLabel {{ color: {t['TEXT']}; background: transparent; }} "
            f"QLabel#RemoteTitle {{ color: {t['MUTED']}; font-family: Consolas; font-weight: 700; }} "
            f"QLineEdit {{ background: {t['INSET']}; color: {t['TEXT']}; border: 1px solid {t['EDGE']}; "
            f"border-radius: 8px; padding: 5px 8px; font-family: Consolas; }} "
            f"QPushButton {{ background: {t['FIELD']}; color: {t['TEXT']}; border: 1px solid {t['EDGE']}; "
            f"border-radius: 8px; padding: 5px 10px; }} QPushButton:hover {{ background: {t['HOVER']}; }} "
            f"QPushButton#RemoteClose {{ border: none; background: transparent; padding: 0; }} "
            f"QPushButton#RemoteClose:hover {{ background: {t['DANGER']}; color: #FFFFFF; border-radius: 7px; }}"
        )
        self.scan.setStyleSheet("font-size: 11px;")
        self.warn.setStyleSheet(f"color: {t['MUTED']}; font-size: 10px;")
        self.tunnel_label.setStyleSheet(f"color: {t['MUTED']}; font-size: 10px;")
        self.send_warning.setStyleSheet(f"color: {t['MUTED']}; font-size: 10px;")
        self.title.label.setStyleSheet(f"color: {t['MUTED']}; font-family: Consolas; font-weight: 700;")
        self.qr.update()
        self._fit_buttons()
