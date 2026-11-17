# -*- coding: utf-8 -*-
"""岗位池批处理：评分 -> 双阈值分流 -> 达标岗位文字化改写。"""
from __future__ import annotations

import datetime as _dt

from core import intent, jobs as job_store, tailor_text
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("pipeline")


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_batch(criteria: dict, profile_text: str, llm: LLMClient, progress=None,
              mode: str = "all", selected_ids=None, force_score: bool = False,
              include_review: bool = False, max_tailor: int | None = None,
              force_tailor: bool = False) -> dict:
    """mode: score / tailor / all。返回真实处理结果，不隐藏单岗失败。"""
    criteria = intent.normalize_criteria(criteria)
    if mode in ("score", "all") and not (
        criteria["directions"] or criteria["cities"] or criteria["salary_min"]
    ):
        raise ValueError("请至少填写目标方向、城市或薪资下限中的一项")
    pool = job_store.load_pool()
    if selected_ids:
        wanted = set(selected_ids)
        scoped = [job for job in pool if job.get("id") in wanted]
    else:
        scoped = list(pool)
    report = {
        "mode": mode,
        "scanned": len(scoped),
        "scored": 0,
        "recommended": 0,
        "review": 0,
        "rejected": 0,
        "needs_detail": 0,
        "tailored": 0,
        "skipped_tailor": 0,
        "reused_tailor": 0,
        "stale_tailor": 0,
        "failures": [],
        "started_at": _now(),
    }

    score_targets = scoped if mode in ("score", "all") else []
    tailor_targets = []
    for index, job in enumerate(score_targets):
        if progress:
            percent = int(2 + (index / max(1, len(score_targets))) * 43)
            progress(percent, "意向评分 %d/%d：%s" % (index + 1, len(score_targets), job.get("title") or "未命名岗位"))
        try:
            result = intent.judge_job(job, criteria, llm, force=force_score)
            job["intent"] = result
            report["scored"] += 1
            if result.get("status") == "recommended":
                report["recommended"] += 1
            elif result.get("status") == "review":
                report["review"] += 1
            elif result.get("status") == "needs_detail":
                report["needs_detail"] += 1
            else:
                report["rejected"] += 1
        except Exception as exc:
            job["intent"] = {
                "status": "error",
                "cache_key": intent.cache_key(job, criteria),
                "criteria_hash": intent.criteria_signature(criteria),
                "jd_hash": job.get("jd_hash") or "",
                "reason": str(exc),
                "judged_at": _now(),
            }
            report["failures"].append({"stage": "score", "job": job.get("title"), "error": str(exc)})
            log.warning("岗位评分失败：%s：%s", job.get("title"), exc)
        if (index + 1) % 5 == 0 or index + 1 == len(score_targets):
            job_store.save_pool(pool)

    if mode in ("tailor", "all"):
        if selected_ids:
            candidates = list(scoped)
        else:
            eligible_status = {"recommended"} | ({"review"} if include_review else set())
            candidates = [
                job for job in scoped
                if (job.get("intent") or {}).get("status") in eligible_status
            ]
        for job in candidates:
            current = tailor_text.result_is_current(job, profile_text, criteria)
            if current:
                report["reused_tailor"] += 1
            elif str((job.get("tailored") or {}).get("text") or "").strip():
                report["stale_tailor"] += 1
            if current and not force_tailor:
                report["skipped_tailor"] += 1
                continue
            tailor_targets.append(job)
        if not selected_ids:
            limit = max_tailor if max_tailor is not None else criteria.get("max_tailor_per_run", 5)
            tailor_targets = tailor_targets[: max(1, int(limit))]
        if not profile_text.strip() and tailor_targets:
            raise ValueError("个人履历为空，无法生成定向文字简历")
        for index, job in enumerate(tailor_targets):
            if progress:
                percent = int(52 + (index / max(1, len(tailor_targets))) * 43)
                progress(percent, "文字改写 %d/%d：%s" % (
                    index + 1, len(tailor_targets), job.get("title") or "未命名岗位"
                ))
            try:
                result = tailor_text.tailor_job(
                    job, profile_text, job.get("intent") or {}, llm,
                    language="中文",
                    strength=criteria.get("rewrite_strength") or "standard",
                    progress=(lambda p, m, _i=index: progress(
                        int(52 + ((_i + max(0, p) / 100.0) / max(1, len(tailor_targets))) * 43), m
                    )) if progress else None,
                )
                result["text"] = result.get("plain_text") or ""
                job["tailored"] = result
                report["tailored"] += 1
            except Exception as exc:
                report["failures"].append({"stage": "tailor", "job": job.get("title"), "error": str(exc)})
                log.warning("文字改写失败：%s：%s", job.get("title"), exc)
            job_store.save_pool(pool)

    job_store.save_pool(pool)
    report["finished_at"] = _now()
    report["pool_counts"] = job_store.status_counts(job_store.load_pool())
    if progress:
        progress(100, "流水线完成：评分 %d，推荐 %d，改写 %d" % (
            report["scored"], report["recommended"], report["tailored"]
        ))
    log.info("流水线完成：%s", report)
    return report
