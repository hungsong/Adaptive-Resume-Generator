# -*- coding: utf-8 -*-
"""Qt 包装：把本地桥接服务的事件安全地送到界面线程。"""
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

from core.bridge import BridgeServer


class BridgeService(QObject):
    connection_changed = pyqtSignal(bool, str)
    event_received = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = BridgeServer(
            on_event=self._on_event,
            on_connection=self._on_connection,
        )
        self.port = 0

    @property
    def connected(self) -> bool:
        return self.server.connected

    def start(self) -> int:
        try:
            self.port = self.server.start()
            return self.port
        except Exception as exc:
            self.failed.emit(str(exc))
            return 0

    def stop(self) -> None:
        self.server.stop()

    def send_command(self, command: dict) -> bool:
        try:
            self.server.send_command(command)
            return True
        except Exception as exc:
            self.failed.emit(str(exc))
            return False

    def _on_event(self, event: dict) -> None:
        self.event_received.emit(dict(event or {}))

    def _on_connection(self, connected: bool, info: dict) -> None:
        info = info or {}
        title = str(info.get("title") or "").strip()
        url = str(info.get("url") or "").strip()
        text = "已连接采集扩展"
        if title:
            text += "：%s" % title
        elif url:
            text += "：%s" % url
        self.connection_changed.emit(bool(connected), text)
