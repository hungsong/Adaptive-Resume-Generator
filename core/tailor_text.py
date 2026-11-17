# -*- coding: utf-8 -*-
"""自由文本履历 -> 岗位定向文字简历。

输出内部按章节/条目组织，但每条事实内容都必须带 source_quotes（从个人履历
逐字摘录的证据）。程序逐条校验摘录是否存在，再做数字、技术名词、措辞检查；
不通过就带反馈重试。最终对外只提供纯文本与 Markdown。
"""
from __future__ import annotations

import datetime as _dt
import hashlib

from core import guard, intent as intent_module, prompts
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("tailor_text")

MAX_ATTEMPTS = 2


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def profile_hash(profile_text: str) -> str:
    return hashlib.sha1(str(profile_text or "").encode("utf-8")).hexdigest()[:16]


def result_is_current(job: dict, profile_text: str, criteria: dict,
                      strength: str | None = None) -> bool:
    """纯本地复用判断：不连接模型，也不产生任何 token 消耗。"""
    result = job.get("tailored") if isinstance(job.get("tailored"), dict) else {}
    if not str(result.get("text") or result.get("plain_text") or "").strip():
        return False
    if result.get("status") == "error":
        return False
    if result.get("jd_hash") != (job.get("jd_hash") or ""):
        return False
    if result.get("profile_hash") != profile_hash(profile_text):
        return False
    criteria = intent_module.normalize_criteria(criteria)
    expected_strength = intent_module.normalize_rewrite_strength(
        strength or criteria.get("rewrite_strength")
    )
    criteria["rewrite_strength"] = expected_strength
    if result.get("criteria_hash") != intent_module.criteria_signature(criteria):
        return False
    if intent_module.normalize_rewrite_strength(result.get("strength")) != expected_strength:
        return False
    return True


def preflight_jobs(jobs: list, profile_text: str, criteria: dict,
                   strength: str | None = None) -> dict:
    """生成前审计：区分可复用、旧结果需更新、从未生成三类岗位。"""
    criteria = intent_module.normalize_criteria(criteria)
    if strength:
        criteria["rewrite_strength"] = intent_module.normalize_rewrite_strength(strength)
    reusable, stale, missing = [], [], []
    for job in jobs or []:
        result = job.get("tailored") if isinstance(job.get("tailored"), dict) else {}
        if result_is_current(job, profile_text, criteria):
            reusable.append(job)
        elif str(result.get("text") or result.get("plain_text") or "").strip():
            stale.append(job)
        else:
            missing.append(job)
    return {
        "criteria": criteria,
        "criteria_hash": intent_module.criteria_signature(criteria),
        "profile_hash": profile_hash(profile_text),
        "strength": criteria["rewrite_strength"],
        "reusable": reusable,
        "stale": stale,
        "missing": missing,
        "total": len(reusable) + len(stale) + len(missing),
        "model_calls_needed": len(stale) + len(missing),
    }


def normalize_sections(data) -> tuple[list, list]:
    sections = []
    issues = []
    for si, raw_section in enumerate(data.get("sections") or [] if isinstance(data, dict) else []):
        if not isinstance(raw_section, dict):
            issues.append({"level": "warn", "kind": "structure", "message": "第 %d 个章节不是对象，已忽略" % (si + 1)})
            continue
        title = str(raw_section.get("title") or "").strip() or "未命名章节"
        items = []
        for ii, raw_item in enumerate(raw_section.get("items") or []):
            if isinstance(raw_item, dict):
                text = str(raw_item.get("text") or "").strip()
                quotes = raw_item.get("source_quotes") or raw_item.get("source_quote") or []
            else:
                text = str(raw_item or "").strip()
                quotes = []
            if isinstance(quotes, str):
                quotes = [quotes]
            quotes = [str(q).strip() for q in quotes if str(q).strip()]
            if not text:
                continue
            items.append({"text": text, "source_quotes": quotes})
        if items:
            sections.append({"title": title, "items": items})
    return sections, issues


def validate_result(data: dict, profile_text: str) -> tuple[list, list, list]:
    sections, structure_issues = normalize_sections(data)
    issues = list(structure_issues)
    requirements = []
    for ri, raw in enumerate(data.get("requirements") or []):
        if not isinstance(raw, dict):
            continue
        requirement = str(raw.get("requirement") or "").strip()
        if not requirement:
            continue
        status = str(raw.get("status") or "gap").strip()
        if status not in ("covered", "weak", "gap"):
            status = "gap"
        quote = str(raw.get("source_quote") or "").strip()
        if status in ("covered", "weak") and not quote:
            issues.append({"level": "warn", "kind": "requirement", "message": "要求「%s」标为%s，但没有证据摘录" % (requirement, status)})
        if quote and guard._norm(quote) not in guard._norm(profile_text):
            issues.append({"level": "error", "kind": "evidence", "message": "要求「%s」的证据摘录在履历中找不到：%s" % (requirement, quote)})
        requirements.append({
            "requirement": requirement,
            "type": str(raw.get("type") or "核心").strip(),
            "status": status,
            "source_quote": quote,
            "note": str(raw.get("note") or "").strip(),
        })

    for si, section in enumerate(sections):
        for ii, item in enumerate(section["items"]):
            label = "%s 第 %d 条" % (section["title"], ii + 1)
            issues.extend(guard.check_free_text_item(
                item["text"], profile_text, item["source_quotes"], label,
            ))
    if not sections:
        issues.append({
            "level": "error", "kind": "quality",
            "message": "模型没有返回任何简历章节，无法生成可用内容",
        })
    return sections, requirements, issues


def build_plain_text(sections: list) -> str:
    lines = []
    for section in sections:
        title = str(section.get("title") or "").strip()
        items = section.get("items") or []
        if not title or not items:
            continue
        if lines:
            lines.append("")
        lines.append(title)
        for item in items:
            text = str(item.get("text") if isinstance(item, dict) else item).strip()
            if text:
                lines.append("- " + text)
    return "\n".join(lines).strip() + ("\n" if lines else "")


def build_markdown(sections: list) -> str:
    lines = []
    for section in sections:
        title = str(section.get("title") or "").strip()
        items = section.get("items") or []
        if not title or not items:
            continue
        if lines:
            lines.append("")
        lines += ["## " + title, ""]
        for item in items:
            text = str(item.get("text") if isinstance(item, dict) else item).strip()
            if text:
                lines.append("- " + text)
    return "\n".join(lines).strip() + ("\n" if lines else "")


def tailor_job(job: dict, profile_text: str, intent: dict, llm: LLMClient,
               language: str = "中文", progress=None,
               strength: str = "standard") -> dict:
    profile_text = str(profile_text or "").strip()
    if len(profile_text) < 80:
        raise ValueError("个人履历太短，请先补充完整履历再生成文字简历")
    strength = intent_module.normalize_rewrite_strength(strength)
    hint = ""
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if progress:
            progress(10 if attempt == 1 else 55, "第 %d 次按岗位改写履历…" % attempt)
        data = llm.complete_json(
            prompts.TAILOR_TEXT_SYSTEM,
            prompts.tailor_text_user(profile_text, job, intent, language, strength) + (("\n\n" + hint) if hint else ""),
            required_keys=["sections"],
            retry_hint="每条内容都必须提供 source_quotes，且必须是个人履历里的逐字原文。",
        )
        sections, requirements, issues = validate_result(data, profile_text)
        errors = guard.blocking(issues)
        log.info("文字改写尝试 %d：章节=%d error=%d warn=%d",
                 attempt, len(sections), len(errors), len(issues) - len(errors))
        result = {
            "sections": sections,
            "requirements": requirements,
            "issues": issues,
            "attempts": attempt,
            "job_summary": str(data.get("job_summary") or "").strip(),
            "editor_notes": [str(x).strip() for x in (data.get("editor_notes") or []) if str(x).strip()],
            "plain_text": build_plain_text(sections),
            "markdown": build_markdown(sections),
            "status": "needs_review" if errors else "ok",
            "model": getattr(llm, "model", ""),
            "profile_hash": profile_hash(profile_text),
            "jd_hash": job.get("jd_hash") or "",
            "criteria_hash": intent.get("criteria_hash") or "",
            "strength": strength,
            "generated_at": _now(),
        }
        if not errors:
            break
        if attempt < MAX_ATTEMPTS:
            hint = prompts.free_text_feedback_user(errors)
    return result
