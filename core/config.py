# -*- coding: utf-8 -*-
"""配置与路径管理。

设计约定：
- 所有可变数据都放在项目目录下（data/、logs/、config.json），不写系统盘。
- config.json 内含 API Key，已在 .gitignore 中排除，不随仓库备份。
- 换模型 / 换服务商只改 config.json，代码零改动。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # 打包成 exe 后，数据目录跟随 exe 所在位置，不写临时解包目录
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
DATA_DIR = APP_DIR / "data"
VERSIONS_DIR = DATA_DIR / "versions"
BACKUP_DIR = DATA_DIR / "backup"
PROFILE_PATH = DATA_DIR / "profile.json"
PROFILE_TEXT_PATH = DATA_DIR / "profile_text.json"
JOBS_DIR = DATA_DIR / "jobs"
JOB_POOL_PATH = JOBS_DIR / "jobs.json"
JOB_DB_PATH = DATA_DIR / "jobs.db"
HIDDEN_JOBS_PATH = JOBS_DIR / "hidden.json"
INTENT_PATH = DATA_DIR / "intent.json"
PROFILES_DIR = DATA_DIR / "profiles"
PROFILES_INDEX_PATH = PROFILES_DIR / "profiles.json"
LOG_DIR = APP_DIR / "logs"

DEFAULT_CONFIG = {
    "api": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key": "",
        "timeout": 120,
        "temperature": 0.3,
        "max_tokens": 4096,
    },
    "resume": {
        "output_language": "中文",
        "summary_max_chars": 260,
    },
    "import": {
        "max_chars": 30000,
        "mark_unconfirmed": True,
    },
    "ui": {
        "theme": "system",
    },
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, VERSIONS_DIR, BACKUP_DIR, JOBS_DIR, PROFILES_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return _deep_merge(DEFAULT_CONFIG, raw)


def save_config(cfg: dict) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def api_config(cfg: dict | None = None) -> dict:
    """返回补齐默认值后的 API 配置。"""
    cfg = cfg or load_config()
    api = dict(cfg.get("api") or {})
    api["provider"] = (api.get("provider") or "deepseek").strip()
    api["api_key"] = (api.get("api_key") or "").strip()
    api["base_url"] = (api.get("base_url") or "").strip() or "https://api.deepseek.com"
    api["model"] = (api.get("model") or "").strip() or "deepseek-chat"
    try:
        api["timeout"] = int(api.get("timeout") or 120)
    except (TypeError, ValueError):
        api["timeout"] = 120
    try:
        api["max_tokens"] = int(api.get("max_tokens") or 4096)
    except (TypeError, ValueError):
        api["max_tokens"] = 4096
    try:
        api["temperature"] = float(api.get("temperature") or 0.3)
    except (TypeError, ValueError):
        api["temperature"] = 0.3
    return api
