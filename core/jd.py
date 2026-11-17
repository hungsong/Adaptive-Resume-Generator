# -*- coding: utf-8 -*-
"""岗位信息解析：粘贴的 JD 文本 -> 结构化岗位信息。"""
from __future__ import annotations

import json

from core import prompts
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("jd")

FIELDS = (
    "company", "role", "responsibilities", "required_skills", "preferred_skills",
    "experience_requirements", "education_requirements", "keywords", "seniority", "language",
)
LIST_FIELDS = (
    "responsibilities", "required_skills", "preferred_skills",
    "experience_requirements", "education_requirements", "keywords",
)


def empty_job() -> dict:
    job = {k: "" for k in FIELDS}
    for k in LIST_FIELDS:
        job[k] = []
    return job


def normalize_job(data) -> dict:
    job = empty_job()
    if not isinstance(data, dict):
        return job
    for k in FIELDS:
        if k in LIST_FIELDS:
            val = data.get(k) or []
            if isinstance(val, str):
                val = [v.strip() for v in val.replace("；", "，").split("，") if v.strip()]
            job[k] = [str(v).strip() for v in val if str(v).strip()] if isinstance(val, list) else []
        else:
            job[k] = str(data.get(k) or "").strip()
    return job


def parse_jd(jd_text: str, llm: LLMClient, progress=None) -> dict:
    jd_text = (jd_text or "").strip()
    if not jd_text:
        raise ValueError("岗位信息为空，请先粘贴 JD 内容")
    if progress:
        progress(30, "正在解析岗位要求…")
    data = llm.complete_json(
        prompts.JD_EXTRACT_SYSTEM,
        prompts.JD_EXTRACT_USER % jd_text,
        required_keys=["role"],
    )
    job = normalize_job(data)
    job["jd_raw"] = jd_text
    if progress:
        progress(90, "岗位解析完成")
    log.info("JD 解析完成：role=%s 必备技能=%d 关键词=%d",
             job.get("role"), len(job["required_skills"]), len(job["keywords"]))
    return job


def summary_lines(job: dict) -> list:
    """给界面展示的若干行摘要。"""
    lines = []
    if job.get("company"):
        lines.append("公司：%s" % job["company"])
    if job.get("role"):
        lines.append("岗位：%s" % job["role"])
    for label, key in (
        ("岗位职责", "responsibilities"),
        ("必备技能", "required_skills"),
        ("加分技能", "preferred_skills"),
        ("经验要求", "experience_requirements"),
        ("学历要求", "education_requirements"),
        ("关键词", "keywords"),
    ):
        vals = job.get(key) or []
        if vals:
            lines.append("%s：%s" % (label, "、".join(vals)))
    return lines
