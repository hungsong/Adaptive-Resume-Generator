# -*- coding: utf-8 -*-
"""Safely remove local runtime data for a clean first-run state.

Only the application's own ``data/``, ``logs/`` and optional ``config.json``
at the project root are eligible.  The guard deliberately rejects paths that
resolve outside that root, including symlinks.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.config import APP_DIR


class DataResetError(RuntimeError):
    """Raised when a reset target is not a safe application-owned path."""


def _safe_target(root: Path, name: str) -> Path:
    source = root / name
    if source.is_symlink():
        raise DataResetError("拒绝删除符号链接：%s" % source)
    target = source.resolve(strict=False)
    if target.parent != root:
        raise DataResetError("拒绝删除应用目录之外的路径：%s" % target)
    return target


def clear_local_data(include_config: bool = False, app_dir: str | Path | None = None) -> dict:
    """Delete local runtime data and return a small audit report.

    ``config.json`` is kept by default so clearing resumes cannot accidentally
    destroy the user's API credentials.  A caller that explicitly asks for it
    can include it in the reset.
    """
    root = Path(app_dir or APP_DIR).resolve(strict=False)
    if not root.is_dir():
        raise DataResetError("应用目录不存在：%s" % root)

    names = ["data", "logs"]
    if include_config:
        names.append("config.json")

    report = {
        "root": str(root),
        "removed": [],
        "missing": [],
        "failures": [],
    }
    for name in names:
        target = _safe_target(root, name)
        if not target.exists():
            report["missing"].append(name)
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            report["removed"].append(name)
        except OSError as exc:
            report["failures"].append({"path": str(target), "error": str(exc)})
    return report
