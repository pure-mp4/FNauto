from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import app_icon


class Tray:
    def __init__(self, shell, theme=None):
        self.shell = shell
        self.available = bool(QSystemTrayIcon.isSystemTrayAvailable())
        self.icon = QSystemTrayIcon(app_icon.icon(), shell)
        self.menu = QMenu()
        self.show_action = QAction("Show", self.menu)
        self.hide_action = QAction("Hide", self.menu)
        self.quit_action = QAction("Quit", self.menu)
        self.show_action.triggered.connect(self._show)
        self.hide_action.triggered.connect(self._hide)
        self.quit_action.triggered.connect(shell.close)
        self.menu.addAction(self.show_action)
        self.menu.addAction(self.hide_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)
        self.icon.setToolTip("FNauto")
        self.retranslate()

    def retranslate(self) -> None:
        self.show_action.setText("Show")
        self.hide_action.setText("Hide")
        self.quit_action.setText("Quit")

    def start(self) -> None:
        self.icon.show()

    def stop(self) -> None:
        self.icon.hide()

    def _show(self) -> None:
        self.shell.show()

    def _hide(self) -> None:
        self.shell.hide()
