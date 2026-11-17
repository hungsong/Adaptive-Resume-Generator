# -*- coding: utf-8 -*-
"""角色工作区：像游戏存档一样隔离履历、意向、岗位池与文字简历。

应用设置（API Key、主题）仍是全局配置；业务数据全部落在
``data/profiles/<角色>/``。切换角色时只切换模块使用的路径，不移动或删除
任何旧文件。首次沿用旧数据时采用复制，原 ``data/`` 文件继续保留。
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import uuid
from pathlib import Path

from core import config
from core.applog import get_logger

log = get_logger("profiles")

SCHEMA_VERSION = 1


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_name(name: str) -> str:
    text = " ".join(str(name or "").split()).strip()
    return text[:60] or "未命名角色"


def _registry_path() -> Path:
    return Path(config.PROFILES_INDEX_PATH)


def _profiles_dir() -> Path:
    return Path(config.PROFILES_DIR)


def _data_root() -> Path:
    return _profiles_dir().parent


def _legacy_paths() -> dict:
    root = _data_root()
    jobs = root / "jobs"
    return {
        "profile_text": root / "profile_text.json",
        "profile": root / "profile.json",
        "intent": root / "intent.json",
        "jobs_dir": jobs,
        "jobs": jobs / "jobs.json",
        # 旧版数据库位于 data/jobs.db，而不是 data/jobs/jobs.db。
        "jobs_db": root / "jobs.db",
        "hidden": jobs / "hidden.json",
        "backup": root / "backup",
        "versions": root / "versions",
    }


def profile_paths(profile_id: str) -> dict:
    base = _profiles_dir() / str(profile_id)
    jobs = base / "jobs"
    return {
        "base": base,
        "profile_text": base / "profile_text.json",
        "profile": base / "profile.json",
        "intent": base / "intent.json",
        "jobs_dir": jobs,
        "jobs": jobs / "jobs.json",
        "jobs_db": jobs / "jobs.db",
        "hidden": jobs / "hidden.json",
        "backup": base / "backup",
        "versions": base / "versions",
    }


def _empty_registry() -> dict:
    return {"schema_version": SCHEMA_VERSION, "active_id": "", "profiles": []}


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("读取失败：%s", path)
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _normalize_record(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("id") or "").strip()
    if not pid or any(sep in pid for sep in ("/", "\\", "..")):
        return None
    return {
        "id": pid,
        "name": _clean_name(raw.get("name")),
        "source": str(raw.get("source") or "blank"),
        "source_file": str(raw.get("source_file") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def load_registry() -> dict:
    raw = _read_json(_registry_path(), {})
    if not isinstance(raw, dict):
        raw = {}
    records = []
    seen = set()
    for item in raw.get("profiles") or []:
        record = _normalize_record(item)
        if record and record["id"] not in seen:
            seen.add(record["id"])
            records.append(record)
    active = str(raw.get("active_id") or "")
    if active not in seen:
        active = ""
    return {"schema_version": SCHEMA_VERSION, "active_id": active, "profiles": records}


def _save_registry(registry: dict) -> dict:
    registry["schema_version"] = SCHEMA_VERSION
    _write_json(_registry_path(), registry)
    return registry


def list_profiles() -> list:
    return list(load_registry().get("profiles") or [])


def get_profile(profile_id: str) -> dict | None:
    for profile in list_profiles():
        if profile["id"] == profile_id:
            return profile
    return None


def active_profile() -> dict | None:
    registry = load_registry()
    active_id = registry.get("active_id") or ""
    return get_profile(active_id) if active_id else None


def legacy_available() -> bool:
    paths = _legacy_paths()
    return any(
        paths[key].exists()
        for key in ("profile_text", "profile", "intent", "jobs", "jobs_db")
    )


def _new_profile_id() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    existing = {p["id"] for p in list_profiles()}
    while True:
        candidate = "role-%s-%s" % (stamp, uuid.uuid4().hex[:5])
        if candidate not in existing:
            return candidate


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_tree(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_dir():
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return True


def _migrated_legacy_text(path: Path) -> str:
    try:
        from core import models

        raw = _read_json(path, {})
        profile = models.normalize_profile(raw)
        from core.profile_text import migrate_from_structured

        return migrate_from_structured(profile)
    except Exception:
        log.exception("旧履历文本转换失败：%s", path)
        return ""


def _adopt_legacy_into(paths: dict) -> None:
    legacy = _legacy_paths()
    _copy_file(legacy["profile_text"], paths["profile_text"])
    _copy_file(legacy["profile"], paths["profile"])
    _copy_file(legacy["intent"], paths["intent"])
    _copy_file(legacy["jobs"], paths["jobs"])
    _copy_file(legacy["jobs_db"], paths["jobs_db"])
    _copy_file(legacy["hidden"], paths["hidden"])
    _copy_tree(legacy["backup"], paths["backup"])
    _copy_tree(legacy["versions"], paths["versions"])

    if not paths["profile_text"].exists() and legacy["profile"].exists():
        text = _migrated_legacy_text(legacy["profile"])
        if text:
            _write_json(paths["profile_text"], {
                "schema_version": 1,
                "text": text,
                "source_file": "",
                "migrated_from": str(legacy["profile"]),
                "updated_at": _now(),
            })


def _write_initial_profile_text(paths: dict, text: str = "", source_file: str = "") -> None:
    if not text and paths["profile_text"].exists():
        return
    _write_json(paths["profile_text"], {
        "schema_version": 1,
        "text": str(text or ""),
        "source_file": str(source_file or ""),
        "migrated_from": "",
        "updated_at": _now() if text else "",
    })


def create_profile(name: str, adopt_legacy: bool = False, initial_text: str = "",
                   source_file: str = "", make_active: bool = True) -> dict:
    """创建角色目录；旧数据只复制，不移动。"""
    registry = load_registry()
    pid = _new_profile_id()
    paths = profile_paths(pid)
    for key in ("base", "jobs_dir", "backup", "versions"):
        paths[key].mkdir(parents=True, exist_ok=True)

    if adopt_legacy:
        _adopt_legacy_into(paths)
    else:
        _write_initial_profile_text(paths, initial_text, source_file)

    record = {
        "id": pid,
        "name": _clean_name(name),
        "source": "legacy" if adopt_legacy else ("resume" if initial_text else "blank"),
        "source_file": str(source_file or ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    registry["profiles"].append(record)
    if make_active:
        registry["active_id"] = pid
    _save_registry(registry)
    if make_active:
        apply_profile(pid)
    log.info("创建角色：%s (%s)，沿用旧数据=%s", record["name"], pid, adopt_legacy)
    return record


def apply_profile(profile_id: str) -> dict:
    """把模块级路径全部指向指定角色。返回角色记录。"""
    record = get_profile(profile_id)
    if not record:
        raise ValueError("角色不存在：%s" % profile_id)
    paths = profile_paths(profile_id)
    for key in ("base", "jobs_dir", "backup", "versions"):
        paths[key].mkdir(parents=True, exist_ok=True)

    config.PROFILE_TEXT_PATH = paths["profile_text"]
    config.PROFILE_PATH = paths["profile"]
    config.INTENT_PATH = paths["intent"]
    config.JOBS_DIR = paths["jobs_dir"]
    config.JOB_POOL_PATH = paths["jobs"]
    config.JOB_DB_PATH = paths["jobs_db"]
    config.HIDDEN_JOBS_PATH = paths["hidden"]
    config.BACKUP_DIR = paths["backup"]
    config.VERSIONS_DIR = paths["versions"]

    from core import intent, job_db, jobs as job_store, profile_text, store

    store.PROFILE_PATH = paths["profile"]
    store.BACKUP_DIR = paths["backup"]
    store.VERSIONS_DIR = paths["versions"]
    profile_text.PROFILE_TEXT_PATH = paths["profile_text"]
    intent.INTENT_PATH = paths["intent"]
    intent.PROFILE_PATH = paths["profile"]
    job_store.JOB_POOL_PATH = paths["jobs"]
    job_store.HIDDEN_JOBS_PATH = paths["hidden"]
    job_db.JOB_DB_PATH = paths["jobs_db"]

    config.ensure_dirs()
    return record


def activate_profile(profile_id: str) -> dict:
    registry = load_registry()
    if not any(p["id"] == profile_id for p in registry["profiles"]):
        raise ValueError("角色不存在：%s" % profile_id)
    registry["active_id"] = profile_id
    _save_registry(registry)
    return apply_profile(profile_id)


def apply_active_profile() -> dict | None:
    record = active_profile()
    if record:
        apply_profile(record["id"])
    return record


def clear_active() -> None:
    registry = load_registry()
    registry["active_id"] = ""
    _save_registry(registry)


def delete_profile(profile_id: str) -> dict:
    """删除非当前角色的工作区；目录先隔离，注册成功后清理。

    当前角色必须先从界面切换出去，避免正在使用的页面和异步任务继续写入
    已删除目录。目录校验、注册表更新和物理清理分开执行，任何一步失败时
    尽量保留可恢复的数据。
    """
    registry = load_registry()
    record = next((p for p in registry["profiles"] if p["id"] == profile_id), None)
    if not record:
        raise ValueError("角色不存在：%s" % profile_id)
    if registry.get("active_id") == profile_id:
        raise ValueError("当前角色不能直接删除，请先切换到其他角色。")

    base = profile_paths(profile_id)["base"]
    profiles_root = _profiles_dir().resolve()
    trash = None
    if base.exists():
        try:
            resolved = base.resolve(strict=True)
        except OSError as exc:
            raise ValueError("无法解析角色目录：%s" % base) from exc
        if resolved.parent != profiles_root or resolved.name != profile_id or not resolved.is_dir():
            raise ValueError("角色目录校验失败，已取消删除：%s" % base)
        trash_root = _profiles_dir() / ".deleted"
        trash_root.mkdir(parents=True, exist_ok=True)
        trash = trash_root / ("%s-%s-%s" % (
            profile_id,
            _dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
            uuid.uuid4().hex[:5],
        ))
        base.replace(trash)

    registry["profiles"] = [p for p in registry["profiles"] if p["id"] != profile_id]
    try:
        _save_registry(registry)
    except Exception:
        if trash and trash.exists() and not base.exists():
            trash.replace(base)
        raise

    if trash:
        try:
            shutil.rmtree(trash)
        except Exception:
            log.exception("角色目录清理失败，已隔离到：%s", trash)
    log.info("删除角色：%s (%s)", record.get("name") or "未命名角色", profile_id)
    return record

