# -*- coding: utf-8 -*-
"""岗位意向匹配：本地硬门槛 + AI 分维度评分 + 双阈值分流。

这一步只回答“这个岗位值不值得我投”，不读取个人履历。达标岗位才会进入
下一步「履历对比 + 文字化改写」。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re

from core import prompts, store
from core.applog import get_logger
from core.config import INTENT_PATH, PROFILE_PATH
from core.jobs import MIN_USABLE_JD_CHARS
from core.llm import LLMClient

log = get_logger("intent")

SCHEMA_VERSION = 1
DIMENSION_WEIGHTS = {
    "direction": 40,
    "responsibilities": 25,
    "industry": 15,
    "salary": 10,
    "level_company": 10,
}
DIMENSION_LABELS = {
    "direction": "岗位方向",
    "responsibilities": "职责内容",
    "industry": "行业背景",
    "salary": "薪资条件",
    "level_company": "职级与公司类型",
}

REWRITE_STRENGTHS = ("precise", "standard", "tactful")
REWRITE_STRENGTH_LABELS = {
    "precise": "精准",
    "standard": "标准",
    "tactful": "委婉",
}
REWRITE_STRENGTH_HINTS = {
    "precise": "更贴近岗位关注点，优先使用岗位同领域的准确表达，但不照搬 JD 句子。",
    "standard": "专业、平衡，既突出匹配点，也保留自然克制的叙述。",
    "tactful": "使用更通用、低针对性的表达，读起来像自然履历，不显出为某岗位专门改写。",
}

CITY_ALIASES = {
    "beijing": "北京", "shanghai": "上海", "shenzhen": "深圳",
    "guangzhou": "广州", "hangzhou": "杭州", "ningbo": "宁波",
    "suzhou": "苏州", "nanjing": "南京", "chengdu": "成都",
    "wuhan": "武汉", "xian": "西安", "xi'an": "西安",
    "chongqing": "重庆", "tianjin": "天津", "qingdao": "青岛",
    "xiamen": "厦门", "dongguan": "东莞", "foshan": "佛山",
    "wuxi": "无锡", "changzhou": "常州", "hefei": "合肥",
}

DEFAULT_CRITERIA = {
    "schema_version": SCHEMA_VERSION,
    "directions": [],
    "cities": [],
    "salary_min": 0,
    "salary_max": 0,
    "remote_ok": True,
    "exclude_words": [],
    "exclude_companies": [],
    "experience": "",
    "education": "",
    "recommend_threshold": 78,
    "review_threshold": 62,
    "min_extension_score": 0,
    "max_tailor_per_run": 5,
    "scan_limit": 30,
    "rewrite_strength": "standard",
}


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value) -> str:
    return str(value or "").strip()


def _int(value, default=0, low=0, high=999999) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def parse_list(value) -> list:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[\n,，;；、]+", str(value or ""))
    out = []
    seen = set()
    for item in raw:
        text = _clean(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def normalize_city_name(value) -> str:
    text = _clean(value)
    key = re.sub(r"\s+", "", text).lower()
    return CITY_ALIASES.get(key, text)


def normalize_rewrite_strength(value) -> str:
    text = _clean(value).lower()
    return text if text in REWRITE_STRENGTHS else "standard"


def normalize_criteria(data) -> dict:
    src = data if isinstance(data, dict) else {}
    out = dict(DEFAULT_CRITERIA)
    for key in ("directions", "cities", "exclude_words", "exclude_companies"):
        out[key] = parse_list(src.get(key))
    out["cities"] = [normalize_city_name(city) for city in out["cities"]]
    out["salary_min"] = _int(src.get("salary_min"), 0, 0, 999)
    out["salary_max"] = _int(src.get("salary_max"), 0, 0, 999)
    if out["salary_max"] and out["salary_min"] > out["salary_max"]:
        out["salary_min"], out["salary_max"] = out["salary_max"], out["salary_min"]
    out["remote_ok"] = bool(src.get("remote_ok", True))
    out["experience"] = _clean(src.get("experience"))
    out["education"] = _clean(src.get("education"))
    out["recommend_threshold"] = _int(src.get("recommend_threshold"), 78, 1, 100)
    out["review_threshold"] = _int(src.get("review_threshold"), 62, 0, 100)
    if out["review_threshold"] > out["recommend_threshold"]:
        out["review_threshold"] = out["recommend_threshold"]
    out["min_extension_score"] = _int(src.get("min_extension_score"), 0, 0, 100)
    out["max_tailor_per_run"] = _int(src.get("max_tailor_per_run"), 5, 1, 50)
    out["scan_limit"] = _int(src.get("scan_limit"), 30, 1, 500)
    out["rewrite_strength"] = normalize_rewrite_strength(src.get("rewrite_strength"))
    return out


def load_criteria() -> dict:
    raw = store.load_json(INTENT_PATH, None)
    if isinstance(raw, dict) and raw:
        return normalize_criteria(raw)
    legacy = store.load_json(PROFILE_PATH, {})
    personal = (legacy.get("personal") or {}) if isinstance(legacy, dict) else {}
    directions = parse_list(personal.get("target"))
    cities = parse_list(personal.get("city"))
    seeded = normalize_criteria({"directions": directions, "cities": cities})
    if directions or cities:
        save_criteria(seeded)
    return seeded


def save_criteria(criteria: dict) -> dict:
    criteria = normalize_criteria(criteria)
    store.backup_file(INTENT_PATH)
    store.write_json_atomic(INTENT_PATH, criteria)
    return criteria


def criteria_signature(criteria: dict) -> str:
    ignored = {"recommend_threshold", "review_threshold", "max_tailor_per_run"}
    source = {k: v for k, v in normalize_criteria(criteria).items() if k not in ignored}
    blob = json.dumps(source, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def cache_key(job: dict, criteria: dict) -> str:
    raw = "%s|%s|%s" % (
        job.get("jd_hash") or "", criteria_signature(criteria),
        (job.get("title") or "").strip(),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _job_text(job: dict) -> str:
    return "\n".join(filter(None, [
        _clean(job.get("title")), _clean(job.get("company")),
        _clean(job.get("city")), _clean(job.get("salary")),
        _clean(job.get("experience")), _clean(job.get("education")),
        _clean(job.get("industry")), _clean(job.get("jd_text")),
    ]))


def parse_salary_range(text: str) -> tuple[float, float] | None:
    """把常见薪资写法换算成 K/月；识别不了就返回 None。"""
    source = _clean(text)
    if not source:
        return None
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[Kk千万元]?\s*[-~－—至到]\s*(\d+(?:\.\d+)?)\s*([Kk千万元]?)",
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
    elif unit == "千":
        pass
    elif unit == "K" or unit == "k":
        pass
    elif "万" in window:
        low *= 10
        high *= 10
        if "年" in window:
            low /= 12
            high /= 12
    if high < low:
        low, high = high, low
    if high <= 0 or low > 500:
        return None
    return round(low, 1), round(high, 1)


def local_gate(job: dict, criteria: dict) -> dict:
    criteria = normalize_criteria(criteria)
    text = _job_text(job)
    lowered = text.lower()
    company = _clean(job.get("company"))
    reasons = []
    notes = []

    for word in criteria["exclude_words"]:
        if word.lower() in lowered:
            reasons.append("命中排除词「%s」" % word)
    for company_word in criteria["exclude_companies"]:
        if company_word.lower() in (company or text).lower():
            reasons.append("命中排除公司「%s」" % company_word)

    salary = parse_salary_range(job.get("salary")) or parse_salary_range(text)
    if salary:
        if criteria["salary_min"] and salary[1] < criteria["salary_min"]:
            reasons.append("薪资上限 %.1fK 低于下限 %dK" % (salary[1], criteria["salary_min"]))
        elif criteria["salary_min"]:
            notes.append("薪资区间 %.1f-%.1fK" % salary)
    elif criteria["salary_min"]:
        notes.append("薪资未识别，未做硬淘汰")

    job_city = _clean(job.get("city"))
    if criteria["cities"]:
        matched_city = next((c for c in criteria["cities"] if c in (job_city or text)), "")
        if matched_city:
            notes.append("城市命中 %s" % matched_city)
        elif criteria["remote_ok"] and re.search(r"远程|remote|居家|homeoffice", text, re.I):
            notes.append("远程岗位")
        elif job_city:
            reasons.append("岗位城市「%s」不在意向城市内" % job_city)
        else:
            notes.append("城市未识别，未做硬淘汰")

    extension_score = _int(job.get("extension_score"), 0, 0, 100)
    if criteria["min_extension_score"] and extension_score < criteria["min_extension_score"]:
        reasons.append("扩展参考分 %d 低于门槛 %d" % (extension_score, criteria["min_extension_score"]))

    if len(_clean(job.get("jd_text"))) < MIN_USABLE_JD_CHARS:
        reasons.append("JD 正文不足 %d 字，请重新采集完整详情" % MIN_USABLE_JD_CHARS)

    return {
        "passed": not reasons,
        "reasons": reasons,
        "notes": notes,
        "salary_range": list(salary) if salary else [],
    }


def _dimension(raw) -> dict:
    if isinstance(raw, dict):
        score = _int(raw.get("score"), 0, 0, 100)
        return {"score": score, "reason": _clean(raw.get("reason"))}
    return {"score": _int(raw, 0, 0, 100), "reason": ""}


def _ai_payload(job: dict, criteria: dict, gate: dict) -> dict:
    return {
        "job": {
            "title": job.get("title") or "",
            "company": job.get("company") or "",
            "city": job.get("city") or "",
            "salary": job.get("salary") or "",
            "experience": job.get("experience") or "",
            "education": job.get("education") or "",
            "company_scale": job.get("company_scale") or "",
            "industry": job.get("industry") or "",
            "jd_text": _clean(job.get("jd_text"))[:9000],
        },
        "intent": criteria,
        "local_gate": gate,
        "weights": DIMENSION_WEIGHTS,
    }


def judge_job(job: dict, criteria: dict, llm: LLMClient, force: bool = False) -> dict:
    criteria = normalize_criteria(criteria)
    if not criteria["directions"] and not criteria["cities"] and not criteria["salary_min"]:
        raise ValueError("请至少填写目标方向、城市或薪资下限中的一项，再运行岗位评分")
    key = cache_key(job, criteria)
    old = job.get("intent") if isinstance(job.get("intent"), dict) else {}
    if not force and old.get("cache_key") == key and old.get("status") in (
        "recommended", "review", "rejected", "needs_detail",
    ):
        fresh = dict(old)
        if fresh.get("status") in ("recommended", "review", "rejected"):
            score = _int(fresh.get("score"), 0, 0, 100)
            if score >= criteria["recommend_threshold"]:
                fresh["status"] = "recommended"
            elif score >= criteria["review_threshold"]:
                fresh["status"] = "review"
            else:
                fresh["status"] = "rejected"
        return fresh

    gate = local_gate(job, criteria)
    base = {
        "cache_key": key,
        "criteria_hash": criteria_signature(criteria),
        "jd_hash": job.get("jd_hash") or "",
        "gate": gate,
        "model": "",
        "judged_at": _now(),
        "dimensions": {},
    }
    if len(_clean(job.get("jd_text"))) < MIN_USABLE_JD_CHARS:
        return {
            **base,
            "score": 0,
            "status": "needs_detail",
            "reason": "JD 正文不足，无法可靠评分",
            "risks": ["请重新扫描并导出完整岗位详情"],
        }
    if not gate["passed"]:
        return {
            **base,
            "score": 0,
            "status": "rejected",
            "reason": "；".join(gate["reasons"]),
            "risks": list(gate["reasons"]),
        }

    data = llm.complete_json(
        prompts.INTENT_SCORE_SYSTEM,
        prompts.intent_score_user(_ai_payload(job, criteria, gate)),
        required_keys=list(DIMENSION_WEIGHTS),
        retry_hint="必须给出 direction / responsibilities / industry / salary / level_company 五个维度的 0-100 分。",
    )
    dimensions = {k: _dimension(data.get(k)) for k in DIMENSION_WEIGHTS}
    total = sum(dimensions[k]["score"] * weight for k, weight in DIMENSION_WEIGHTS.items()) / 100.0
    score = int(round(total))
    if score >= criteria["recommend_threshold"]:
        status = "recommended"
    elif score >= criteria["review_threshold"]:
        status = "review"
    else:
        status = "rejected"
    risks = data.get("risks") or []
    if isinstance(risks, str):
        risks = [risks]
    result = {
        **base,
        "score": score,
        "status": status,
        "dimensions": dimensions,
        "reason": _clean(data.get("summary") or data.get("reason")),
        "risks": [_clean(x) for x in risks if _clean(x)],
        "model": getattr(llm, "model", ""),
    }
    log.info("意向评分：%s -> %s %d 分", job.get("title"), status, score)
    return result
