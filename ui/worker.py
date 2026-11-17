# -*- coding: utf-8 -*-
"""后台任务线程：耗时操作（调用大模型等）一律走这里，界面不卡死。"""
from __future__ import annotations

import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from core.applog import get_logger

log = get_logger("worker")


class Worker(QThread):
    """执行 fn(progress_cb)；进度实时上报，结果与异常通过信号回主线程。"""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn(self._emit_progress)
        except Exception as exc:  # 保证异常可见：写日志 + 弹窗提示
            log.error("后台任务失败：%s\n%s", exc, traceback.format_exc())
            self.failed.emit(str(exc))
            return
        self.done.emit(result)

    def _emit_progress(self, percent, message=""):
        try:
            self.progress.emit(int(percent), str(message))
        except Exception:
            pass


class WorkerKeeper:
    """持有运行中的线程引用，避免被 Python 垃圾回收导致崩溃。"""

    def __init__(self):
        self._alive = []

    def start(self, worker: Worker) -> Worker:
        self._alive.append(worker)
        worker.finished.connect(lambda: self._alive.remove(worker) if worker in self._alive else None)
        worker.start()
        return worker

    def busy(self) -> bool:
        return bool(self._alive)
