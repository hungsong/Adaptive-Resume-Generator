# -*- coding: utf-8 -*-
"""JSON 读写：原子写入 + 自动备份，绝不破坏用户既有数据。"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
from pathlib import Path

from core import models
from core.applog import get_logger
from core.config import BACKUP_DIR, PROFILE_PATH, VERSIONS_DIR, ensure_dirs

log = get_logger("store")

MAX_BACKUPS = 20


def _atomic_write_json(path: Path, data) -> None:
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_json_atomic(path: Path, data) -> None:
    """公开的原子写入入口，供岗位池/意向配置等模块复用。"""
    _atomic_write_json(path, data)


def backup_file(path: Path) -> None:
    """写入前先备份旧文件，并只保留最近 MAX_BACKUPS 份。"""
    if not path.exists():
        return
    ensure_dirs()
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = BACKUP_DIR / f"{path.stem}-{stamp}{path.suffix}"
    try:
        shutil.copy2(path, dst)
    except OSError:
        log.exception("备份失败：%s", path)
        return
    olds = sorted(
        BACKUP_DIR.glob(f"{path.stem}-*{path.suffix}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in olds[MAX_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("读取失败，返回默认值：%s", path)
        return default


# ---------------------------------------------------------------- 主履历

def load_profile() -> dict:
    return models.normalize_profile(load_json(PROFILE_PATH, {}))


def save_profile(profile: dict) -> dict:
    profile = models.normalize_profile(profile)
    backup_file(PROFILE_PATH)
    _atomic_write_json(PROFILE_PATH, profile)
    return profile


def profile_hash(profile: dict) -> str:
    blob = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- 简历版本

def _version_path(vid: str) -> Path:
    return VERSIONS_DIR / f"{vid}.json"


def new_version_id(kind: str, existing: list[str] | None = None) -> str:
    existing = set(existing or [])
    stamp = _dt.datetime.now().strftime("%Y%m%d")
    n = 1
    while f"{stamp}-{kind}-{n:02d}" in existing or _version_path(f"{stamp}-{kind}-{n:02d}").exists():
        n += 1
    return f"{stamp}-{kind}-{n:02d}"


def version_ids() -> list[str]:
    ensure_dirs()
    return sorted((p.stem for p in VERSIONS_DIR.glob("*.json")), reverse=True)


def list_versions() -> list:
    """版本摘要（不含正文），按创建时间倒序。"""
    out = []
    for vid in version_ids():
        doc = load_json(_version_path(vid), None)
        if not isinstance(doc, dict):
            continue
        out.append(
            {
                "id": doc.get("id") or vid,
                "kind": doc.get("kind") or "basic",
                "title": doc.get("title") or vid,
                "created_at": doc.get("created_at") or "",
                "model": doc.get("model") or "",
                "job_role": ((doc.get("job") or {}).get("role") or ""),
            }
        )
    out.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return out


def load_version(vid: str) -> dict | None:
    doc = load_json(_version_path(vid), None)
    return doc if isinstance(doc, dict) else None


def save_version(doc: dict) -> str:
    vid = str(doc.get("id") or "").strip()
    if not vid:
        vid = new_version_id(str(doc.get("kind") or "basic"))
        doc["id"] = vid
    if not doc.get("created_at"):
        doc["created_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    backup_file(_version_path(vid))
    _atomic_write_json(_version_path(vid), doc)
    return vid


def delete_version(vid: str) -> bool:
    path = _version_path(vid)
    if not path.exists():
        return False
    backup_file(path)
    try:
        path.unlink()
        return True
    except OSError:
        log.exception("删除版本失败：%s", vid)
        return False
