# -*- coding: utf-8 -*-
"""岗位与文字简历的本地 SQLite 留存。

JSON 岗位池仍是对外兼容与恢复入口；本模块在每次保存岗位池时同步写入
SQLite，保存可筛选的岗位字段、评分记录和“岗位—文字简历”配对。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
from pathlib import Path

from core.applog import get_logger
from core.config import JOB_DB_PATH

log = get_logger("job_db")


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect(path=None):
    target = Path(path or JOB_DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path=None) -> None:
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT,
                job_id TEXT,
                title TEXT,
                company TEXT,
                city TEXT,
                salary_text TEXT,
                salary_min REAL,
                salary_max REAL,
                experience TEXT,
                education TEXT,
                industry TEXT,
                company_scale TEXT,
                jd_text TEXT,
                jd_hash TEXT,
                extension_score INTEGER DEFAULT 0,
                extension_action TEXT,
                favorited INTEGER DEFAULT 0,
                scanned_at TEXT,
                imported_at TEXT,
                updated_at TEXT,
                active INTEGER DEFAULT 1,
                raw_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(extension_score);
            CREATE INDEX IF NOT EXISTS idx_jobs_salary ON jobs(salary_max);
            CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs(city);
            CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(active);

            CREATE TABLE IF NOT EXISTS job_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                criteria_hash TEXT,
                jd_hash TEXT,
                score INTEGER,
                status TEXT,
                dimensions_json TEXT,
                gate_json TEXT,
                reason TEXT,
                risks_json TEXT,
                model TEXT,
                judged_at TEXT,
                UNIQUE(job_id, cache_key)
            );
            CREATE INDEX IF NOT EXISTS idx_scores_job ON job_scores(job_id);
            CREATE INDEX IF NOT EXISTS idx_scores_score ON job_scores(score);
            CREATE INDEX IF NOT EXISTS idx_scores_status ON job_scores(status);

            CREATE TABLE IF NOT EXISTS resume_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                profile_hash TEXT NOT NULL,
                criteria_hash TEXT NOT NULL,
                jd_hash TEXT NOT NULL,
                status TEXT,
                plain_text TEXT,
                sections_json TEXT,
                issues_json TEXT,
                manually_edited INTEGER DEFAULT 0,
                generated_at TEXT,
                updated_at TEXT,
                UNIQUE(job_id, profile_hash, criteria_hash, jd_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_resume_job ON resume_outputs(job_id);
            CREATE INDEX IF NOT EXISTS idx_resume_generated ON resume_outputs(generated_at);

            CREATE TABLE IF NOT EXISTS scan_runs (
                scan_id TEXT PRIMARY KEY,
                status TEXT,
                criteria_json TEXT,
                started_at TEXT,
                finished_at TEXT,
                report_json TEXT
            );
            """
        )


def _salary_range(text: str) -> tuple[float, float] | None:
    source = str(text or "").strip()
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[Kk千万元]?\s*[-~－—至到]\s*"
        r"(\d+(?:\.\d+)?)\s*([Kk千万元]?)",
        source,
    )
    if not match:
        return None
    low, high, unit = float(match.group(1)), float(match.group(2)), match.group(3)
    window = source[max(0, match.start() - 8): match.end() + 10]
    if unit == "万":
        low *= 10
        high *= 10
        if "年" in window and "月" not in window:
            low /= 12
            high /= 12
    elif unit == "元":
        low /= 1000
        high /= 1000
    elif not unit and "万" in window:
        low *= 10
        high *= 10
        if "年" in window:
            low /= 12
            high /= 12
    if high < low:
        low, high = high, low
    if high <= 0 or low > 500:
        return None
    return round(low, 2), round(high, 2)


def _json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


def sync_pool(jobs: list, path=None) -> None:
    """把当前 JSON 岗位池镜像到 SQLite，并追加评分与简历版本。"""
    init_db(path)
    jobs = [j for j in (jobs or []) if isinstance(j, dict) and j.get("id")]
    with _connect(path) as conn:
        conn.execute("UPDATE jobs SET active = 0")
        for job in jobs:
            salary = _salary_range(job.get("salary"))
            conn.execute(
                """
                INSERT INTO jobs (
                    id, url, job_id, title, company, city, salary_text,
                    salary_min, salary_max, experience, education, industry,
                    company_scale, jd_text, jd_hash, extension_score,
                    extension_action, favorited, scanned_at, imported_at,
                    updated_at, active, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url=excluded.url, job_id=excluded.job_id, title=excluded.title,
                    company=excluded.company, city=excluded.city,
                    salary_text=excluded.salary_text, salary_min=excluded.salary_min,
                    salary_max=excluded.salary_max, experience=excluded.experience,
                    education=excluded.education, industry=excluded.industry,
                    company_scale=excluded.company_scale, jd_text=excluded.jd_text,
                    jd_hash=excluded.jd_hash, extension_score=excluded.extension_score,
                    extension_action=excluded.extension_action, favorited=excluded.favorited,
                    scanned_at=excluded.scanned_at, imported_at=excluded.imported_at,
                    updated_at=excluded.updated_at, active=1, raw_json=excluded.raw_json
                """,
                (
                    str(job.get("id")), job.get("url") or "", job.get("job_id") or "",
                    job.get("title") or "", job.get("company") or "", job.get("city") or "",
                    job.get("salary") or "", salary[0] if salary else None,
                    salary[1] if salary else None, job.get("experience") or "",
                    job.get("education") or "", job.get("industry") or "",
                    job.get("company_scale") or "", job.get("jd_text") or "",
                    job.get("jd_hash") or "", int(job.get("extension_score") or 0),
                    job.get("extension_action") or "", 1 if job.get("favorited") else 0,
                    job.get("scanned_at") or "", job.get("imported_at") or "",
                    job.get("updated_at") or "", _json(job),
                ),
            )
            intent = job.get("intent") if isinstance(job.get("intent"), dict) else {}
            if intent.get("score") is not None or intent.get("status"):
                cache_key = str(intent.get("cache_key") or "{}:{}".format(
                    intent.get("criteria_hash") or "", intent.get("judged_at") or _now()
                ))
                conn.execute(
                    """
                    INSERT INTO job_scores (
                        job_id, cache_key, criteria_hash, jd_hash, score, status,
                        dimensions_json, gate_json, reason, risks_json, model, judged_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, cache_key) DO UPDATE SET
                        score=excluded.score, status=excluded.status,
                        dimensions_json=excluded.dimensions_json,
                        gate_json=excluded.gate_json, reason=excluded.reason,
                        risks_json=excluded.risks_json, model=excluded.model,
                        judged_at=excluded.judged_at
                    """,
                    (
                        str(job.get("id")), cache_key,
                        intent.get("criteria_hash") or "", intent.get("jd_hash") or "",
                        int(intent.get("score") or 0), intent.get("status") or "",
                        _json(intent.get("dimensions") or {}), _json(intent.get("gate") or {}),
                        intent.get("reason") or "", _json(intent.get("risks") or []),
                        intent.get("model") or "", intent.get("judged_at") or "",
                    ),
                )
            tailored = job.get("tailored") if isinstance(job.get("tailored"), dict) else {}
            if tailored.get("text"):
                conn.execute(
                    """
                    INSERT INTO resume_outputs (
                        job_id, profile_hash, criteria_hash, jd_hash, status,
                        plain_text, sections_json, issues_json, manually_edited,
                        generated_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, profile_hash, criteria_hash, jd_hash) DO UPDATE SET
                        status=excluded.status, plain_text=excluded.plain_text,
                        sections_json=excluded.sections_json, issues_json=excluded.issues_json,
                        manually_edited=excluded.manually_edited,
                        updated_at=excluded.updated_at
                    """,
                    (
                        str(job.get("id")), tailored.get("profile_hash") or "",
                        tailored.get("criteria_hash") or "", tailored.get("jd_hash") or job.get("jd_hash") or "",
                        tailored.get("status") or "", tailored.get("text") or "",
                        _json(tailored.get("sections") or []),
                        _json(tailored.get("issues") or []),
                        1 if tailored.get("manually_edited") else 0,
                        tailored.get("generated_at") or "",
                        tailored.get("edited_at") or tailored.get("generated_at") or _now(),
                    ),
                )
        conn.commit()


def record_scan_start(scan_id: str, criteria: dict, path=None) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO scan_runs (scan_id, status, criteria_json, started_at)
            VALUES (?, 'running', ?, ?)
            ON CONFLICT(scan_id) DO UPDATE SET
                status='running', criteria_json=excluded.criteria_json,
                started_at=excluded.started_at, finished_at=NULL, report_json=NULL
            """,
            (str(scan_id), _json(criteria), _now()),
        )
        conn.commit()


def record_scan_finish(scan_id: str, status: str, report=None, path=None) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            "UPDATE scan_runs SET status=?, finished_at=?, report_json=? WHERE scan_id=?",
            (status, _now(), _json(report or {}), str(scan_id)),
        )
        conn.commit()


def summary(path=None) -> dict:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM jobs WHERE active=1) AS jobs,
                (SELECT COUNT(*) FROM job_scores) AS scores,
                (SELECT COUNT(*) FROM resume_outputs) AS resumes,
                (SELECT COUNT(*) FROM scan_runs) AS scans
            """
        ).fetchone()
    return dict(row) if row else {"jobs": 0, "scores": 0, "resumes": 0, "scans": 0}
