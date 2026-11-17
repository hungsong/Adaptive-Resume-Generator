# -*- coding: utf-8 -*-
"""浏览器实时回传岗位的单岗处理流水线。

扩展只负责页面遍历和岗位正文采集；本模块在桌面端按顺序完成去重入库、
意向评分与达标岗位文字简历生成。单条岗位失败会记录在返回值里，不阻断后续岗位。
"""
from __future__ import annotations

import datetime as _dt

from core import intent, job_db, jobs as job_store, tailor_text
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("live")


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def process_live_job(job: dict, criteria: dict, profile: str, llm: LLMClient,
                     auto_tailor: bool = True, include_review: bool = False) -> dict:
    """处理一条实时岗位并持久化，返回可展示的单岗结果。"""
    criteria = intent.normalize_criteria(criteria)
    pool = job_store.load_pool()
    pool, merge_report = job_store.merge_jobs(pool, [job])
    job_store.save_pool(pool)

    incoming = job_store.normalize_job(job)
    if not incoming:
        raise ValueError("扩展回传的岗位缺少标题、链接或 JD")
    current = job_store.find_job(pool, incoming["id"])
    if not current:
        raise ValueError("岗位去重入库后未能找到记录")

    result = {
        "id": current.get("id"),
        "title": current.get("title") or "未命名岗位",
        "company": current.get("company") or "",
        "merge": merge_report,
        "score": None,
        "status": "error",
        "score_error": "",
        "tailored": False,
        "tailor_error": "",
    }

    try:
        score = intent.judge_job(current, criteria, llm)
        current["intent"] = score
        result["score"] = score.get("score")
        result["status"] = score.get("status") or "error"
    except Exception as exc:
        current["intent"] = {
            "status": "error",
            "cache_key": intent.cache_key(current, criteria),
            "criteria_hash": intent.criteria_signature(criteria),
            "jd_hash": current.get("jd_hash") or "",
            "reason": str(exc),
            "judged_at": _now(),
        }
        result["score_error"] = str(exc)
        log.warning("实时岗位评分失败：%s：%s", result["title"], exc)

    eligible = {"recommended"} | ({"review"} if include_review else set())
    should_tailor = bool(
        auto_tailor
        and result["status"] in eligible
        and len(str(profile or "").strip()) >= 80
    )
    if should_tailor and not tailor_text.result_is_current(current, profile, criteria):
        try:
            tailored = tailor_text.tailor_job(
                current, profile, current.get("intent") or {}, llm,
                language="中文",
                strength=criteria.get("rewrite_strength") or "standard",
            )
            tailored["text"] = tailored.get("plain_text") or ""
            current["tailored"] = tailored
            result["tailored"] = bool(tailored.get("text"))
        except Exception as exc:
            current["tailored"] = {
                "status": "error",
                "reason": str(exc),
                "jd_hash": current.get("jd_hash") or "",
                "profile_hash": tailor_text.profile_hash(profile),
                "criteria_hash": intent.criteria_signature(criteria),
                "strength": criteria.get("rewrite_strength") or "standard",
                "generated_at": _now(),
            }
            result["tailor_error"] = str(exc)
            log.warning("实时文字简历生成失败：%s：%s", result["title"], exc)

    job_store.save_pool(pool)
    result["usability"] = current.get("usability") or ""
    result["salary"] = current.get("salary") or ""
    result["city"] = current.get("city") or ""
    return result


def scan_counts(scan_id: str = "") -> dict:
    """返回本地岗位库摘要，附带扫描编号，供界面结束提示使用。"""
    data = job_db.summary()
    data["scan_id"] = scan_id
    return data
