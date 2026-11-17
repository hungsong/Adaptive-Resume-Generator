# -*- coding: utf-8 -*-
"""统一日志：滚动文件日志（logs/app.log），界面可另挂 handler 显示到窗口。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from core.config import LOG_DIR, ensure_dirs

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_logger_name = "resume"
_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _configured
    root = logging.getLogger(_logger_name)
    if _configured:
        return root
    ensure_dirs()
    root.setLevel(logging.DEBUG)
    root.propagate = False
    fh = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(sh)
    _configured = True
    return root


def get_logger(name: str = "app") -> logging.Logger:
    setup_logging()
    return logging.getLogger(_logger_name).getChild(name)


def shutdown_logging() -> None:
    """Flush and close file handlers before local logs are removed.

    Windows keeps an open log file locked, so the reset flow must release the
    rotating handler (and the in-app log panel handler) before deleting logs.
    """
    global _configured
    root = logging.getLogger(_logger_name)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass
    _configured = False
