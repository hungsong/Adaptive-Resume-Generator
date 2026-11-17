# -*- coding: utf-8 -*-
"""数据结构定义：主履历（唯一事实源）与简历文档（版本）。

主履历 profile：
{
  "schema_version": 1,
  "personal": {"name","phone","email","city","target","links","note"},
  "sections": {
     "work":       [{"id":"w1","org":"","role":"","start":"","end":"","raw":"","confirmed":true}],
     "projects":   [...],
     "education":  [...],
     "skills":     [{"id":"s1","text":"","confirmed":true}],
     "certificates":[...],
     "achievements":[...]
  }
}

简历文档 resume doc：
{
  "id","kind","title","created_at","model","profile_hash",
  "job": {...} | None, "match_matrix": [...] | [],
  "header": {"name","phone","email","city","target","links"},
  "summary": "",
  "sections": [
     {"key":"work","title":"工作经历","items":[
        {"entry_id":"w1","org":"","role":"","start":"","end":"",
         "bullets":[{"text":"","evidence_ids":["w1"],"flagged":false}]}]}
  ]
}

关键约束：组织结构性事实（公司 / 职位 / 时间 / 学校 / 证书名）一律由程序
从主履历逐字复制，AI 只负责 summary 与 bullets 的文字 —— 这是防虚构的第一道
结构性保障（见 core/generate.py）。
"""
from __future__ import annotations

import re

PERSONAL_FIELDS = [
    ("name", "姓名"),
    ("phone", "电话"),
    ("email", "邮箱"),
    ("city", "城市"),
    ("target", "求职意向"),
    ("links", "链接（GitHub / 主页，可多行）"),
    ("note", "备注（可选，不写入简历正文）"),
]

SECTION_SPECS = [
    {
        "key": "work",
        "title": "工作经历",
        "kind": "timeline",
        "id_prefix": "w",
        "item_fields": [
            ("org", "公司"),
            ("role", "职位"),
            ("start", "开始时间"),
            ("end", "结束时间"),
        ],
        "detail_label": "工作内容（每行一条，写你自己的原话即可，AI 只做表达优化）",
    },
    {
        "key": "projects",
        "title": "项目经历",
        "kind": "timeline",
        "id_prefix": "p",
        "item_fields": [
            ("org", "项目名称"),
            ("role", "担任角色"),
            ("start", "开始时间"),
            ("end", "结束时间"),
        ],
        "detail_label": "项目内容（每行一条）",
    },
    {
        "key": "education",
        "title": "教育经历",
        "kind": "timeline",
        "id_prefix": "e",
        "item_fields": [
            ("org", "学校"),
            ("role", "学历 / 专业"),
            ("start", "开始时间"),
            ("end", "结束时间"),
        ],
        "detail_label": "补充说明（每行一条，可留空）",
    },
    {
        "key": "skills",
        "title": "技能",
        "kind": "list",
        "id_prefix": "s",
        "item_fields": [("text", "技能（可写熟练程度，如 Python（熟练））")],
        "detail_label": "",
    },
    {
        "key": "certificates",
        "title": "证书",
        "kind": "list",
        "id_prefix": "c",
        "item_fields": [("text", "证书名称（可附时间）")],
        "detail_label": "",
    },
    {
        "key": "achievements",
        "title": "工作成果",
        "kind": "list",
        "id_prefix": "a",
        "item_fields": [("text", "成果（一句话）")],
        "detail_label": "",
    },
]

SECTION_MAP = {s["key"]: s for s in SECTION_SPECS}
SECTION_ORDER = [s["key"] for s in SECTION_SPECS]

# 简历正文的章节顺序（summary 由程序单独处理）
RESUME_SECTION_ORDER = [
    "summary", "work", "projects", "education", "skills", "certificates", "achievements",
]
RESUME_SECTION_TITLES = {
    "summary": "个人简介",
    "work": "工作经历",
    "projects": "项目经历",
    "education": "教育经历",
    "skills": "技能",
    "certificates": "证书",
    "achievements": "工作成果",
}

SCHEMA_VERSION = 1


def empty_profile() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "personal": {k: "" for k, _ in PERSONAL_FIELDS},
        "sections": {s["key"]: [] for s in SECTION_SPECS},
    }


def _dedupe_ids(entries: list, prefix: str) -> list:
    used = set()
    n = 1
    for e in entries:
        eid = str(e.get("id") or "")
        if not eid or eid in used:
            while f"{prefix}{n}" in used:
                n += 1
            eid = f"{prefix}{n}"
        used.add(eid)
        e["id"] = eid
    return entries


def normalize_profile(data) -> dict:
    """把任意来源的履历数据补齐成标准结构（缺字段不报错，只补默认值）。"""
    prof = empty_profile()
    if not isinstance(data, dict):
        return prof
    personal = data.get("personal") or {}
    if isinstance(personal, dict):
        for k, _ in PERSONAL_FIELDS:
            prof["personal"][k] = str(personal.get(k) or "")
    secs = data.get("sections") or {}
    if not isinstance(secs, dict):
        secs = {}
    for spec in SECTION_SPECS:
        key = spec["key"]
        items = secs.get(key) or []
        out = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                entry = {"id": str(it.get("id") or "")}
                for fk, _label in spec["item_fields"]:
                    entry[fk] = str(it.get(fk) or "").strip()
                if spec["kind"] == "timeline":
                    entry["raw"] = str(it.get("raw") or "").strip()
                entry["confirmed"] = bool(it.get("confirmed", True))
                out.append(entry)
        prof["sections"][key] = _dedupe_ids(out, spec["id_prefix"])
    return prof


def next_entry_id(section_key: str, entries: list) -> str:
    spec = SECTION_MAP[section_key]
    used = {str(e.get("id")) for e in entries}
    n = 1
    while f"{spec['id_prefix']}{n}" in used:
        n += 1
    return f"{spec['id_prefix']}{n}"


def iter_entries(profile: dict, section_key: str) -> list:
    return (profile.get("sections") or {}).get(section_key) or []


def find_entry(profile: dict, section_key: str, entry_id: str) -> dict | None:
    for e in iter_entries(profile, section_key):
        if str(e.get("id")) == str(entry_id):
            return e
    return None


def entry_display(section_key: str, entry: dict) -> str:
    """列表里显示的一行摘要。"""
    spec = SECTION_MAP.get(section_key)
    if not spec:
        return str(entry)
    if spec["kind"] == "list":
        return entry.get("text") or "（空）"
    org = entry.get("org") or "（未填公司/名称）"
    role = entry.get("role") or ""
    start = entry.get("start") or ""
    end = entry.get("end") or ""
    period = f"{start} - {end}".strip(" -")
    tail = " · ".join([p for p in (role, period) if p])
    flag = "" if entry.get("confirmed", True) else "  [待确认]"
    return f"{org}  {tail}{flag}"


def entry_details(entry: dict) -> list:
    """条目里的细节行（raw 按行拆分）。"""
    raw = entry.get("raw") or ""
    return [ln.strip() for ln in re.split(r"\r?\n+", raw) if ln.strip()]


def profile_corpus(profile: dict) -> str:
    """主履历的全部文字，用于本地真实性校验。"""
    chunks = []
    for v in (profile.get("personal") or {}).values():
        chunks.append(str(v or ""))
    for spec in SECTION_SPECS:
        for e in iter_entries(profile, spec["key"]):
            for k, v in e.items():
                if k in ("confirmed", "id"):
                    continue
                chunks.append(str(v or ""))
    return "\n".join(chunks)


def empty_resume_doc(kind: str = "basic", title: str = "") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": "",
        "kind": kind,
        "title": title,
        "created_at": "",
        "model": "",
        "profile_hash": "",
        "job": None,
        "match_matrix": [],
        "header": {k: "" for k, _ in PERSONAL_FIELDS if k != "note"},
        "summary": "",
        "sections": [],
    }
