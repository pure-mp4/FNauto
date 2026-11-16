import os

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

import config
import i18n


def grab_primary_screen() -> QImage:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QImage()
    return screen.grabWindow(0).toImage()


class SnipOverlay(QWidget):
    def __init__(
        self, key: str, lang: str = "en", on_done=None, image=None, path: str = "", fullscreen: bool = True, parent=None
    ):
        super().__init__(parent)
        self.key, self.lang = key, i18n.norm(lang)
        self.on_done = on_done or (lambda _path, _error=None: None)
        self.image = image if isinstance(image, QImage) else grab_primary_screen()
        self.path = path or config.external_template_path(key, self.lang)
        self.fullscreen = bool(fullscreen)
        self.start = None
        self.end = None
        self._closed = False
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        if self.fullscreen:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self.setGeometry(screen.geometry())
        else:
            self.resize(self.image.size() if not self.image.isNull() else self.size())

    def _display_image(self) -> QImage:
        if self.image.isNull() or self.width() <= 0 or self.height() <= 0:
            return self.image
        if self.image.width() == self.width() and self.image.height() == self.height():
            return self.image
        return self.image.scaled(self.width(), self.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def _selection(self):
        if self.start is None or self.end is None:
            return None
        x0, x1 = sorted((self.start.x(), self.end.x()))
        y0, y1 = sorted((self.start.y(), self.end.y()))
        return x0, y0, x1, y1

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self.rect(), self._display_image())
        sel = self._selection()
        if sel is not None:
            x0, y0, x1, y1 = sel
            p.setPen(QPen(QColor("#EF4444"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRect(QPoint(x0, y0), QPoint(x1, y1)))
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            point = event.position().toPoint()
            self.start = point
            self.end = point
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start is not None and event.buttons() & Qt.LeftButton:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.start is None:
            return
        self.end = event.position().toPoint()
        x0, y0, x1, y1 = self._selection()
        if x1 - x0 < 5 or y1 - y0 < 5:
            self._close(None)
            return
        image = self._display_image()
        sx = image.width() / max(1, self.width())
        sy = image.height() / max(1, self.height())
        rx0, ry0 = int(x0 * sx), int(y0 * sy)
        rw, rh = max(1, int((x1 - x0) * sx)), max(1, int((y1 - y0) * sy))
        if (x1 - x0) * (y1 - y0) > 0.15 * image.width() * image.height():
            self._close(None, i18n.t(self.lang, "log_too_large"))
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            crop = image.copy(rx0, ry0, rw, rh)
            if not crop.save(self.path):
                raise OSError("could not save image")
        except Exception as e:
            self._close(None, i18n.t(self.lang, "log_capture_error", error=e))
            return
        self._close(self.path)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._close(None)
            return
        super().keyPressEvent(event)

    def _close(self, path, error=None) -> None:
        if self._closed:
            return
        self._closed = True
        self.close()
        self.on_done(path, error)
