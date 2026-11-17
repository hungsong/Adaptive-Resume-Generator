# -*- coding: utf-8 -*-
"""个人履历自由文本：唯一事实源。

不再要求用户按公司/项目/时间线拆分，只保存一份可直接编辑的长文本。
旧版结构化履历会被转换成可读文本迁入，但不会删除旧文件。
"""
from __future__ import annotations

import datetime as _dt

from core import models, store
from core.config import PROFILE_TEXT_PATH

SCHEMA_VERSION = 1


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def empty_profile_text() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "text": "",
        "source_file": "",
        "migrated_from": "",
        "updated_at": "",
    }


def migrate_from_structured(profile: dict) -> str:
    lines = []
    personal = profile.get("personal") or {}
    for key, label in models.PERSONAL_FIELDS:
        value = str(personal.get(key) or "").strip()
        if value and key != "note":
            lines.append("%s：%s" % (label.split("（", 1)[0], value))
    for spec in models.SECTION_SPECS:
        entries = models.iter_entries(profile, spec["key"])
        if not entries:
            continue
        lines += ["", "【%s】" % spec["title"]]
        for entry in entries:
            if spec["kind"] == "timeline":
                head = "  ".join(str(entry.get(k) or "").strip() for k, _ in spec["item_fields"])
                if head.strip():
                    lines.append(head.strip())
                raw = str(entry.get("raw") or "").strip()
                if raw:
                    lines.extend("  " + line.strip() for line in raw.splitlines() if line.strip())
            else:
                text = str(entry.get("text") or "").strip()
                if text:
                    lines.append("- " + text)
    return "\n".join(lines).strip()


def load_profile_text() -> dict:
    data = store.load_json(PROFILE_TEXT_PATH, None)
    if isinstance(data, str):
        data = {"text": data}
    if isinstance(data, dict):
        out = empty_profile_text()
        out.update({k: data.get(k, out[k]) for k in out})
        out["text"] = str(out.get("text") or "")
        return out

    legacy = store.load_profile()
    migrated = migrate_from_structured(legacy)
    out = empty_profile_text()
    if migrated:
        out["text"] = migrated
        out["migrated_from"] = str(store.PROFILE_PATH)
        out["updated_at"] = _now()
        save_profile_text(out["text"], migrated_from=out["migrated_from"])
    return out


def save_profile_text(text: str, source_file: str = "", migrated_from: str = "") -> dict:
    old = store.load_json(PROFILE_TEXT_PATH, {})
    old = old if isinstance(old, dict) else {}
    data = {
        "schema_version": SCHEMA_VERSION,
        "text": str(text or ""),
        "source_file": str(source_file or old.get("source_file") or ""),
        "migrated_from": str(migrated_from or old.get("migrated_from") or ""),
        "updated_at": _now(),
    }
    store.backup_file(PROFILE_TEXT_PATH)
    store.write_json_atomic(PROFILE_TEXT_PATH, data)
    return data


def text_stats(text: str) -> dict:
    value = str(text or "")
    return {
        "chars": len(value),
        "non_space_chars": len("".join(value.split())),
        "lines": len([line for line in value.splitlines() if line.strip()]),
    }
