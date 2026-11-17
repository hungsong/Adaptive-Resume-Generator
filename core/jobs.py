# -*- coding: utf-8 -*-
"""岗位池：扩展导出的 JSON -> 去重、校验、持久化。

兼容两种导出：
1. 新版：{"schema_version":1, "source":"boss", "jobs":[...]}
2. 旧版：{"records":[...]}

岗位一旦存在，重新导入时保留已有评分与文字简历；若 JD 正文发生变化，
则让旧的评分/改写结果失效，避免拿旧结论套新岗位。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from core import job_db, store
from core.applog import get_logger
from core.config import HIDDEN_JOBS_PATH, JOB_POOL_PATH

log = get_logger("jobs")

SCHEMA_VERSION = 1
MIN_USABLE_JD_CHARS = 120

JOB_TEXT_FIELDS = (
    "job_id", "url", "title", "company", "city", "salary", "experience",
    "education", "company_scale", "industry", "jd_text", "extension_reason",
    "extension_action", "scanned_at", "source",
)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value, limit: int = 0) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit] if limit > 0 else text


def canonical_url(url: str) -> str:
    raw = _clean(url)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except Exception:
        return raw.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def job_id_from_url(url: str) -> str:
    match = re.search(r"/job_detail/([^/?#]+)", str(url or ""), re.I)
    if not match:
        return ""
    return re.sub(r"\.html?$", "", match.group(1), flags=re.I)


def stable_key(job: dict) -> str:
    basis = canonical_url(job.get("url") or "") or _clean(job.get("job_id"))
    if not basis:
        basis = "|".join([
            _clean(job.get("title")), _clean(job.get("company")),
            _clean(job.get("jd_text"))[:500],
        ])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def jd_hash(job: dict) -> str:
    text = _clean(job.get("jd_text"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "是", "已收藏")


def _number(value, default=0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _from_normalized(raw: dict) -> dict:
    return {
        "job_id": _clean(raw.get("job_id")),
        "url": _clean(raw.get("url") or raw.get("href")),
        "title": _clean(raw.get("title")),
        "company": _clean(raw.get("company")),
        "city": _clean(raw.get("city")),
        "salary": _clean(raw.get("salary")),
        "experience": _clean(raw.get("experience")),
        "education": _clean(raw.get("education")),
        "company_scale": _clean(raw.get("company_scale") or raw.get("companyScale")),
        "industry": _clean(raw.get("industry")),
        "jd_text": _clean(raw.get("jd_text") or raw.get("jd_raw"), 30000),
        "extension_score": _number(raw.get("extension_score") or raw.get("score")),
        "extension_reason": _clean(raw.get("extension_reason") or raw.get("mainReason"), 4000),
        "extension_action": _clean(raw.get("extension_action") or raw.get("action")),
        "favorited": _bool(raw.get("favorited")),
        "scanned_at": _clean(raw.get("scanned_at") or raw.get("time")),
        "source": _clean(raw.get("source")) or "boss",
    }


def _from_legacy_record(raw: dict) -> dict:
    return _from_normalized({
        "job_id": job_id_from_url(raw.get("href")),
        "url": raw.get("href"),
        "title": raw.get("title"),
        "company_scale": raw.get("companyScale"),
        "jd_text": raw.get("detailText") or raw.get("detail_text") or raw.get("cardText"),
        "score": raw.get("score"),
        "mainReason": raw.get("mainReason") or raw.get("decisionLog"),
        "action": raw.get("action"),
        "favorited": raw.get("action") == "favorite",
        "time": raw.get("time"),
        "source": "boss",
    })


def normalize_job(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if "records" in raw or "jobs" in raw:
        return None
    if raw.get("href") and not raw.get("url"):
        job = _from_legacy_record(raw)
    else:
        job = _from_normalized(raw)
    job["url"] = canonical_url(job.get("url"))
    if not job.get("job_id"):
        job["job_id"] = job_id_from_url(job["url"])
    job["jd_text"] = job["jd_text"].strip()
    if not (job.get("title") or job.get("jd_text") or job.get("job_id")):
        return None
    key = stable_key(job)
    job["id"] = key
    job["jd_hash"] = jd_hash(job)
    job["usability"] = "ok" if len(job["jd_text"]) >= MIN_USABLE_JD_CHARS else "short_jd"
    job.setdefault("intent", {})
    job.setdefault("tailored", {})
    job["imported_at"] = _clean(raw.get("imported_at")) or _now()
    job["updated_at"] = _clean(raw.get("updated_at")) or job["imported_at"]
    return job


def _extract_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    if isinstance(jobs, list):
        return jobs
    records = payload.get("records")
    if isinstance(records, list):
        return records
    if any(k in payload for k in ("url", "href", "title", "jd_text", "detailText")):
        return [payload]
    return []


def _merge_one(old: dict, new: dict) -> tuple[dict, str, bool]:
    """返回 (合并结果, 状态 added/updated/unchanged, JD 是否变化)。"""
    old_jd_hash = old.get("jd_hash") or jd_hash(old)
    changed = old_jd_hash != new["jd_hash"]
    if not changed:
        merged = dict(old)
        for key in JOB_TEXT_FIELDS:
            if new.get(key) not in (None, "", []):
                merged[key] = new[key]
        merged["extension_score"] = new.get("extension_score", old.get("extension_score", 0))
        merged["favorited"] = bool(old.get("favorited") or new.get("favorited"))
        merged["updated_at"] = _now()
        material_change = any(
            str(old.get(key) or "") != str(new.get(key) or "")
            for key in ("title", "company", "city", "salary", "extension_score")
        )
        return merged, ("updated" if material_change else "unchanged"), False

    merged = dict(old)
    for key in JOB_TEXT_FIELDS:
        merged[key] = new.get(key, "")
    merged.update({
        "id": new["id"], "jd_hash": new["jd_hash"], "usability": new["usability"],
        "extension_score": new.get("extension_score", 0),
        "favorited": new.get("favorited", False),
        "imported_at": old.get("imported_at") or new.get("imported_at") or _now(),
        "updated_at": _now(),
        "intent": {},
        "tailored": {},
    })
    return merged, "updated", True


def merge_jobs(existing: list, incoming: list) -> tuple[list, dict]:
    by_id = {str(j.get("id")): j for j in existing if isinstance(j, dict) and j.get("id")}
    report = {
        "added": 0, "updated": 0, "unchanged": 0, "invalid": 0,
        "jd_changed": 0, "short_jd": 0, "total_received": 0,
    }
    for raw in incoming:
        report["total_received"] += 1
        new = normalize_job(raw)
        if not new:
            report["invalid"] += 1
            continue
        if new["usability"] == "short_jd":
            report["short_jd"] += 1
        old = by_id.get(new["id"])
        if not old:
            by_id[new["id"]] = new
            report["added"] += 1
            continue
        merged, state, changed = _merge_one(old, new)
        by_id[new["id"]] = merged
        report[state] += 1
        if changed:
            report["jd_changed"] += 1
    jobs = sorted(
        by_id.values(),
        key=lambda j: (str(j.get("scanned_at") or ""), str(j.get("imported_at") or "")),
        reverse=True,
    )
    report["pool_total"] = len(jobs)
    return jobs, report


def load_pool() -> list:
    data = store.load_json(JOB_POOL_PATH, [])
    if isinstance(data, dict):
        data = data.get("jobs") or []
    if not isinstance(data, list):
        return []
    jobs = []
    for raw in data:
        job = normalize_job(raw)
        if not job:
            continue
        job["id"] = _clean(raw.get("id")) or job["id"]
        job["intent"] = raw.get("intent") if isinstance(raw.get("intent"), dict) else {}
        job["tailored"] = raw.get("tailored") if isinstance(raw.get("tailored"), dict) else {}
        jobs.append(job)
    return jobs


def save_pool(jobs: list) -> None:
    store.backup_file(JOB_POOL_PATH)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "count": len(jobs),
        "jobs": jobs,
    }
    store.write_json_atomic(JOB_POOL_PATH, payload)
    try:
        job_db.sync_pool(jobs)
    except Exception:
        log.exception("岗位池写入 SQLite 失败，JSON 数据已保留")


def import_file(path) -> dict:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError("无法读取 JSON：%s" % exc) from exc
    items = _extract_items(payload)
    if not items:
        raise ValueError("JSON 里没有找到 jobs 或 records 数组")
    existing = load_pool()
    jobs, report = merge_jobs(existing, items)
    save_pool(jobs)
    if isinstance(payload, dict):
        report["source"] = payload.get("source") or ""
        report["scan_id"] = payload.get("scan_id") or ""
    report["file"] = str(path)
    log.info("岗位池导入完成：%s", report)
    return report


def clear_pool() -> None:
    save_pool([])


def load_hidden() -> set[str]:
    """读取当前角色下被“清空当前列表”隐藏的岗位 ID。"""
    raw = store.load_json(HIDDEN_JOBS_PATH, [])
    if isinstance(raw, dict):
        raw = raw.get("ids") or []
    if not isinstance(raw, list):
        return set()
    return {str(value) for value in raw if str(value)}


def save_hidden(ids) -> set[str]:
    values = sorted({str(value) for value in (ids or []) if str(value)})
    store.write_json_atomic(HIDDEN_JOBS_PATH, {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "ids": values,
    })
    return set(values)


def hide_jobs(ids) -> set[str]:
    values = load_hidden()
    values.update(str(value) for value in (ids or []) if str(value))
    return save_hidden(values)


def unhide_all() -> None:
    save_hidden([])


def find_job(jobs: list, job_id: str) -> dict | None:
    for job in jobs:
        if job.get("id") == job_id:
            return job
    return None


def status_counts(jobs: list) -> dict:
    counts = {"all": len(jobs), "unscored": 0, "recommended": 0, "review": 0,
              "rejected": 0, "needs_detail": 0, "error": 0, "tailored": 0, "short_jd": 0}
    for job in jobs:
        if job.get("usability") == "short_jd":
            counts["short_jd"] += 1
        intent = job.get("intent") or {}
        status = intent.get("status") or "unscored"
        if status not in ("recommended", "review", "rejected", "needs_detail", "error"):
            status = "unscored"
        counts[status] += 1
        if (job.get("tailored") or {}).get("text"):
            counts["tailored"] += 1
    return counts


def display_name(job: dict) -> str:
    title = _clean(job.get("title")) or "未命名岗位"
    company = _clean(job.get("company"))
    return "%s · %s" % (company, title) if company else title
