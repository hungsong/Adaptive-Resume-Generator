# -*- coding: utf-8 -*-
"""岗位要求 <-> 主履历证据 的匹配矩阵。

LLM 只做初判，程序负责复核：evidence_ids 必须在主履历里真实存在，
状态与证据不一致时由本地规则纠正（宁可保守，也不许拔高）。
"""
from __future__ import annotations

import json

from core import models, prompts
from core.applog import get_logger
from core.llm import LLMClient

log = get_logger("match")

STATUSES = ("已覆盖", "表达不足", "证据不足", "真实缺口")
TYPES = ("必备", "加分")


def all_entry_ids(profile: dict) -> list:
    ids = []
    for spec in models.SECTION_SPECS:
        ids.extend(str(e.get("id")) for e in models.iter_entries(profile, spec["key"]))
    return ids


def entry_exists(profile: dict, entry_id: str) -> bool:
    return any(
        models.find_entry(profile, spec["key"], entry_id) is not None
        for spec in models.SECTION_SPECS
    )


def build_matrix(job: dict, profile: dict, llm: LLMClient, progress=None) -> list:
    """返回匹配矩阵行列表（含 selected 标记，供界面勾选重点）。"""
    if progress:
        progress(30, "正在比对岗位要求与你的履历…")
    ids = all_entry_ids(profile)
    data = llm.complete_json(
        prompts.EVIDENCE_MATCH_SYSTEM,
        prompts.EVIDENCE_MATCH_USER % (
            json.dumps(job, ensure_ascii=False, indent=2),
            json.dumps(profile, ensure_ascii=False, indent=2),
            "、".join(ids) or "（无）",
        ),
        required_keys=["matrix"],
    )
    rows = []
    for raw in data.get("matrix") or []:
        if not isinstance(raw, dict):
            continue
        requirement = str(raw.get("requirement") or "").strip()
        if not requirement:
            continue
        evidence = [str(x) for x in (raw.get("evidence_ids") or []) if entry_exists(profile, str(x))]
        status = str(raw.get("status") or "").strip()
        if status not in STATUSES:
            status = "证据不足"
        if status == "已覆盖" and not evidence:
            status = "证据不足"
        if evidence and status == "真实缺口":
            status = "证据不足"
        rtype = str(raw.get("type") or "").strip()
        if rtype not in TYPES:
            rtype = "必备" if "必" in rtype or not rtype else "加分"
        rows.append({
            "requirement": requirement,
            "type": rtype,
            "evidence_ids": evidence,
            "status": status,
            "note": str(raw.get("note") or "").strip(),
            "selected": True,
        })
    log.info("匹配矩阵：共 %d 条要求，真实缺口 %d 条",
             len(rows), sum(1 for r in rows if r["status"] == "真实缺口"))
    if progress:
        progress(90, "匹配完成")
    return rows


def selected_entry_ids(matrix: list, checked_ids: list) -> list:
    """用户勾选的履历条目 + 勾选的重点要求所引用的条目。"""
    out = []
    for eid in checked_ids:
        if eid not in out:
            out.append(eid)
    for row in matrix or []:
        if not row.get("selected", True):
            continue
        for eid in row.get("evidence_ids") or []:
            if eid not in out:
                out.append(eid)
    return out


def real_gaps(matrix: list) -> list:
    return [r for r in (matrix or []) if r.get("status") == "真实缺口"]
