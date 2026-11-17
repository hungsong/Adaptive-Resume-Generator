# -*- coding: utf-8 -*-
"""通用控件与日志桥接。"""
from __future__ import annotations

import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QDoubleSpinBox, QPlainTextEdit, QSpinBox


class LogEmitter(QObject):
    message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    """把 logging 记录转发到界面上的日志面板。"""

    def __init__(self, emitter: LogEmitter, level=logging.INFO):
        super().__init__(level)
        self.emitter = emitter
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            self.emitter.message.emit(self.format(record))
        except Exception:
            pass


class LogPanel(QPlainTextEdit):
    """只读日志面板，最多保留 500 行，可一键清空。"""

    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(self.MAX_LINES)

    def append_line(self, text: str) -> None:
        self.appendPlainText(text)


class NoWheelSpinBox(QSpinBox):
    """未获得焦点时不响应滚轮，避免滚动页面误改分数与阈值。"""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """同 NoWheelSpinBox，适用于小数设置。"""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
