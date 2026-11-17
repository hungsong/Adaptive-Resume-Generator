# -*- coding: utf-8 -*-
"""生成管道：主履历 -> 基础简历 / 自适应简历；旧简历文本 -> 主履历。

关键设计（防虚构的第一道保障）：
LLM 只输出「选哪些条目 + 每条要点的文字」，公司名 / 职位 / 时间 / 学校 / 证书名
一律由程序按 entry_id 从主履历逐字复制，模型没有机会改写这些结构性事实。

生成后交给 core/guard.py 做本地校验；有 error 就带着违规点重试一次，仍不过则标红交给用户。
"""
from __future__ import annotations

import datetime as _dt

from core import guard, models, prompts, store
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("generate")

MAX_ATTEMPTS = 2
HEADER_KEYS = ("name", "phone", "email", "city", "target", "links")


def _copy_header(profile: dict) -> dict:
    personal = profile.get("personal") or {}
    return {k: str(personal.get(k) or "") for k in HEADER_KEYS}


def _assemble(llm_out: dict, profile: dict, kind: str, title: str,
              job=None, matrix=None, model: str = ""):
    """把 LLM 的文字结果与主履历的结构性事实拼成简历文档。"""
    doc = models.empty_resume_doc(kind, title)
    doc["header"] = _copy_header(profile)
    doc["summary"] = str(llm_out.get("summary") or "").strip()
    doc["job"] = job
    doc["match_matrix"] = matrix or []
    doc["model"] = model

    issues = []
    sections_out = []
    for sec in llm_out.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        key = str(sec.get("key") or "").strip()
        spec = models.SECTION_MAP.get(key)
        if spec is None:
            issues.append({
                "level": "error", "kind": "structure",
                "message": "模型返回了未知章节「%s」" % key, "path": [key],
            })
            continue
        items_out = []
        if spec["kind"] == "timeline":
            for idx, item in enumerate(sec.get("items") or []):
                if not isinstance(item, dict):
                    continue
                eid = str(item.get("entry_id") or "").strip()
                entry = models.find_entry(profile, key, eid) if eid else None
                if entry is None:
                    issues.append({
                        "level": "error", "kind": "structure",
                        "message": "模型引用了主履历中不存在的条目 entry_id=%s（%s）" % (eid or "空", spec["title"]),
                        "path": [key, idx],
                    })
                    continue
                bullets = []
                for b in item.get("bullets") or []:
                    text = b.get("text") if isinstance(b, dict) else b
                    text = str(text or "").strip()
                    if not text:
                        continue
                    bullets.append({"text": text, "evidence_ids": [eid], "flagged": False})
                items_out.append({
                    "entry_id": eid,
                    "org": entry.get("org", ""),
                    "role": entry.get("role", ""),
                    "start": entry.get("start", ""),
                    "end": entry.get("end", ""),
                    "bullets": bullets,
                })
        else:
            for raw_item in sec.get("items") or []:
                text = raw_item.get("text") if isinstance(raw_item, dict) else raw_item
                text = str(text or "").strip()
                if not text:
                    continue
                evidence = [
                    e["id"] for e in models.iter_entries(profile, key)
                    if str(e.get("text") or "").strip() == text
                ]
                items_out.append({"text": text, "evidence_ids": evidence, "flagged": False})
        if items_out:
            sections_out.append({"key": key, "title": spec["title"], "items": items_out})

    order = {s["key"]: i for i, s in enumerate(models.SECTION_SPECS)}
    sections_out.sort(key=lambda s: order.get(s["key"], 99))
    doc["sections"] = sections_out
    return doc, issues


def _run(llm: LLMClient, system: str, user_builder, profile: dict, kind: str, title: str,
         job=None, matrix=None, progress=None):
    """生成 + 校验 +（必要时）带反馈重试一次。"""
    hint = ""
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if progress:
            progress(20 if attempt == 1 else 60, "第 %d 次生成中（模型：%s）…" % (attempt, llm.model))
        llm_out = llm.complete_json(system, user_builder(hint), required_keys=["sections"])
        doc, issues = _assemble(llm_out, profile, kind, title, job, matrix, llm.model)
        all_issues = issues + guard.check_resume(doc, profile)
        errors = guard.blocking(all_issues)
        log.info(
            "生成尝试 %d：error=%d warn=%d 章节=%d",
            attempt, len(errors), len(all_issues) - len(errors), len(doc.get("sections") or []),
        )
        guard.flag_document(doc, all_issues)
        result = {"doc": doc, "issues": all_issues, "attempts": attempt}
        if not errors:
            return result
        if attempt < MAX_ATTEMPTS:
            hint = prompts.guard_feedback_user(errors)
    return result


def generate_basic_resume(profile: dict, llm: LLMClient, language: str = "中文", progress=None) -> dict:
    """履历 -> 基础简历。"""
    if progress:
        progress(5, "正在整理主履历…")
    return _run(
        llm,
        prompts._NORMALIZE_SYSTEM,
        lambda hint: prompts.basic_resume_user(profile, language) + (("\n\n" + hint) if hint else ""),
        profile,
        "basic",
        "基础简历",
        progress=progress,
    )


def generate_tailored_resume(profile: dict, job: dict, allowed_entry_ids: list,
                             llm: LLMClient, language: str = "中文",
                             matrix=None, progress=None) -> dict:
    """主履历 + 岗位 -> 自适应简历（只允许使用勾选过的条目）。"""
    if progress:
        progress(5, "正在按岗位重组内容…")
    title = "%s · %s" % (job.get("company") or "目标岗位", job.get("role") or "未命名岗位")
    return _run(
        llm,
        prompts._NORMALIZE_SYSTEM,
        lambda hint: prompts.tailored_resume_user(profile, job, allowed_entry_ids, language)
        + (("\n\n" + hint) if hint else ""),
        profile,
        "tailored",
        title.strip(" ·"),
        job=job,
        matrix=matrix,
        progress=progress,
    )


def import_profile_from_text(text: str, llm: LLMClient, mark_unconfirmed: bool = True,
                             progress=None) -> dict:
    """旧简历文本 -> 主履历结构（不润色、不补全；导入的条目标记为「待确认」）。"""
    if progress:
        progress(30, "正在解析旧简历文本…")
    data = llm.complete_json(
        prompts.IMPORT_RESUME_SYSTEM,
        prompts.IMPORT_RESUME_USER % text,
        required_keys=["sections"],
    )
    profile = models.normalize_profile(data)
    if mark_unconfirmed:
        for spec in models.SECTION_SPECS:
            for entry in models.iter_entries(profile, spec["key"]):
                entry["confirmed"] = False
    if progress:
        progress(90, "解析完成")
    return profile


def finalize_doc(doc: dict, profile: dict, kind: str, title: str, model: str,
                 job=None, matrix=None) -> dict:
    """补上版本元信息（id / 时间 / 履历指纹）后返回，可直接交给 store 保存。"""
    doc["kind"] = kind
    doc["title"] = title
    doc["model"] = model
    doc["job"] = job
    doc["match_matrix"] = matrix or []
    doc["profile_hash"] = store.profile_hash(profile)
    doc["created_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc["id"] = store.new_version_id(kind)
    return doc
