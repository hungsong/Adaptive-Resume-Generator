# -*- coding: utf-8 -*-
"""本地真实性校验（零 API 成本）—— 本项目最核心的模块。

思路参考 Resume-Matcher（services/resume_preservation.py 的"确定性保护 + 偏差评估"、
docs/agent/architecture/prompt-workflow-design.md 的"本地评估 + 少量重试"），按本项目的
需求重写：

简历里的结构性事实（公司 / 职位 / 时间 / 学校 / 证书名）由程序从主履历逐字复制，
所以这里重点核查 AI 写出来的文字（简介 / 要点 / 技能行）：

1. structure  引用的条目是否真实存在、是否引用了「待确认」条目
2. number     数字 / 百分比必须能在主履历里找到
3. skill      技能行必须在主履历里有依据
4. entity     英文技术名词、引号术语必须能在主履历里找到
5. wording    不得把「参与」升级成「负责」、「了解」升级成「熟练」
6. quality    空内容、单条过长等表达问题

结果结构：[{"level": "error"|"warn", "kind": ..., "message": ..., "path": [...]}]
error = 阻断（触发重试并标红），warn = 提示（界面标黄）。
"""
from __future__ import annotations

import datetime as _dt
import re

from core import models

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_EN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./_-]{1,}")
_QUOTED_RE = re.compile(r"[《「【]([^》」】]{1,24})[》」】]|（([^（）]{1,24})）|「([^」]{1,24})」")
_SPLIT_RE = re.compile(r"[、,，/／;；|\s]+")

# 强化词 -> 主履历里需要出现的支撑表述（概念对得上才算有依据）
# 这里刻意不做「同义词宽松匹配」：主履历里找不到对应表述就提示用户确认，
# 宁可多提示一次，也不放过一次凭空拔高。
_SUPPORT_OF = {
    "负责": ("负责", "主导", "牵头", "统筹", "带领", "管理", "独立负责", "全面负责"),
    "主导": ("主导", "牵头", "负责", "推动"),
    "牵头": ("牵头", "主导", "负责"),
    "推动": ("推动", "主导", "牵头", "负责"),
    "统筹": ("统筹", "主导", "负责", "管理"),
    "带领": ("带领", "管理", "负责"),
    "管理": ("管理", "带领", "负责"),
    "精通": ("精通", "熟练"),
    "熟练": ("熟练", "精通"),
    "独立负责": ("独立负责", "独立完成"),
    "独立完成": ("独立完成", "独立负责"),
    "全面负责": ("全面负责", "负责"),
    "深度参与": ("深度参与", "参与"),
}

_LEVEL_WORDS = ("熟练", "精通", "了解", "掌握", "熟悉", "一般", "良好", "优秀", "较强的", "较强的")

_EN_STOPWORDS = frozenset("""
a an the of and or to in on at for with by from as is are was were be been being am
this that these those it its it's we you they he she his her their our your my
using use used uses via per etc eg ie about into over under than then there here
project projects system systems team teams work works working job role company
develop develop develop develop develop
""".split())

MAX_BULLET_CHARS = 140
MAX_SUMMARY_CHARS = 260


def _norm(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _canon_num(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        a, b = s.split(".", 1)
        a = a.lstrip("0") or "0"
        b = b.rstrip("0")
        return (a + "." + b) if b else a
    return s.lstrip("0") or "0"


def _numbers(text) -> set:
    out = set()
    for m in _NUM_RE.finditer(str(text or "")):
        raw = m.group(0)
        out.add(_canon_num(raw))
        if "." in raw:  # 2020.03 -> 2020 与 3，避免把年月拆开算成虚构
            for part in raw.split("."):
                if part:
                    out.add(_canon_num(part))
    return out


_DATE_RE = re.compile(r"((?:19|20)\d{2})\s*(?:[.\-/年]\s*(\d{1,2})\s*月?)?")
_PRESENT_WORDS = ("至今", "现在", "present", "now")
_DATE_RANGE_RE = re.compile(
    r"((?:19|20)\d{2})\s*(?:[.\-/年]\s*(\d{1,2})\s*月?)?\s*[-~－—至到]\s*"
    r"((?:19|20)\d{2})\s*(?:[.\-/年]\s*(\d{1,2})\s*月?)?"
)


def _parse_ym(text):
    """把 2020.03 / 2020-3 / 2020年3月 解析成 (年, 月)。"""
    s = str(text or "").strip()
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 1
    if not 1 <= month <= 12:
        month = 1
    return (year, month)


def allowed_year_counts(profile: dict) -> set:
    """由主履历的起止时间推算「N 年经验」，允许 N / N+1 两种取整写法。"""
    out = set()
    today = _dt.date.today()
    for spec in models.SECTION_SPECS:
        if spec["kind"] != "timeline":
            continue
        for entry in models.iter_entries(profile, spec["key"]):
            start = _parse_ym(entry.get("start"))
            if not start:
                continue
            end_text = str(entry.get("end") or "")
            if not end_text.strip() or any(w in end_text.lower() for w in _PRESENT_WORDS):
                end = (today.year, today.month)
            else:
                end = _parse_ym(end_text)
            if not end:
                continue
            months = (end[0] * 12 + end[1]) - (start[0] * 12 + start[1])
            if months <= 0 or months > 600:
                continue
            years = months / 12.0
            for c in {int(years), int(years) + 1, round(years)}:
                if c > 0:
                    out.add(str(c))
    return out


def allowed_year_counts_from_text(text: str) -> set:
    """从自由文本的日期区间推算允许出现的「N 年经验」。"""
    out = set()
    source = str(text or "")
    today = _dt.date.today()
    for match in _DATE_RANGE_RE.finditer(source):
        start = (int(match.group(1)), int(match.group(2) or 1))
        end = (int(match.group(3)), int(match.group(4) or 1))
        months = (end[0] * 12 + end[1]) - (start[0] * 12 + start[1])
        if 0 < months <= 600:
            years = months / 12.0
            for count in {int(years), int(years) + 1, round(years)}:
                if count > 0:
                    out.add(str(count))
    for match in re.finditer(
        r"((?:19|20)\d{2})\s*(?:[.\-/年]\s*(\d{1,2})\s*月?)?\s*[-~－—至到]?\s*(?:至今|现在|present|now)",
        source, re.I,
    ):
        start = (int(match.group(1)), int(match.group(2) or 1))
        months = (today.year * 12 + today.month) - (start[0] * 12 + start[1])
        if 0 < months <= 600:
            years = months / 12.0
            for count in {int(years), int(years) + 1, round(years)}:
                if count > 0:
                    out.add(str(count))
    return out


def _en_tokens(text) -> set:
    return {m.group(0) for m in _EN_RE.finditer(str(text or ""))}


def _quoted_terms(text) -> set:
    out = set()
    for m in _QUOTED_RE.finditer(str(text or "")):
        for g in m.groups():
            if g and g.strip():
                out.add(g.strip())
    return out


def _skill_core(text) -> str:
    t = re.sub(r"[（(][^）)]*[）)]", "", str(text or ""))
    for w in _LEVEL_WORDS:
        t = t.replace(w, "")
    return _norm(t)


def check_resume(doc: dict, profile: dict, extra_issues=None) -> list:
    """返回违规清单（error 阻断 / warn 提示）。"""
    issues = list(extra_issues or [])
    corpus = models.profile_corpus(profile)
    corpus_norm = _norm(corpus)
    corpus_tokens = {t.lower() for t in _en_tokens(corpus)}
    corpus_numbers = _numbers(corpus)
    allowed_years = allowed_year_counts(profile)

    def add(level, kind, message, path=None):
        issues.append(
            {"level": level, "kind": kind, "message": message, "path": list(path or [])}
        )

    def check_text(text, label, source_text, path, max_chars=MAX_BULLET_CHARS):
        text = str(text or "").strip()
        if not text:
            add("error", "quality", "%s：内容为空" % label, path)
            return
        if len(text) > max_chars:
            add("warn", "quality", "%s：共 %d 字，偏长，建议精简" % (label, len(text)), path)
        for m in _NUM_RE.finditer(text):
            n = _canon_num(m.group(0))
            if n in corpus_numbers:
                continue
            if text[m.end():].lstrip().startswith("年") and n in allowed_years:
                continue  # 由履历起止时间推算出的「N 年」，属于可核实的推导
            add("error", "number", "%s：出现主履历中查不到的数字「%s」" % (label, n), path)
        for tok in sorted(_en_tokens(text)):
            low = tok.lower()
            if len(low) < 2 or low in _EN_STOPWORDS:
                continue
            if low in corpus_tokens:
                continue
            add("warn", "entity", "%s：出现主履历中没有的技术名词「%s」，请确认是否真实" % (label, tok), path)
        for term in sorted(_quoted_terms(text)):
            if _norm(term) and _norm(term) not in corpus_norm:
                add("warn", "entity", "%s：出现履历中没有的术语「%s」" % (label, term), path)
        src = _norm(source_text)
        if src:
            for w, supports in _SUPPORT_OF.items():
                if w in text and w not in src and not any(s in src for s in supports):
                    add(
                        "warn",
                        "wording",
                        "%s：使用了「%s」这类强化表述，但主履历对应内容里缺少支撑" % (label, w),
                        path,
                    )

    def check_skill(text, label, path):
        core = _skill_core(text)
        if not core:
            add("error", "quality", "%s：技能内容为空" % label, path)
            return
        for part in [p for p in _SPLIT_RE.split(core) if p]:
            if part not in corpus_norm:
                add("error", "skill", "%s：技能「%s」在主履历里找不到依据" % (label, part), path)

    # ---------------------------------------------------------- 简介
    summary = str(doc.get("summary") or "").strip()
    if not summary:
        add("warn", "quality", "个人简介为空，简历缺少开篇概述", ["summary"])
    else:
        check_text(summary, "个人简介", corpus, ["summary"], max_chars=MAX_SUMMARY_CHARS)

    # ---------------------------------------------------------- 章节
    for si, sec in enumerate(doc.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        key = str(sec.get("key") or "")
        spec = models.SECTION_MAP.get(key)
        if spec is None:
            add("warn", "structure", "未知章节「%s」已忽略" % key, [key])
            continue
        title = sec.get("title") or spec["title"]
        items = sec.get("items") or []
        if not items:
            continue
        for ii, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            path = [key, ii]
            if spec["kind"] == "timeline":
                eid = str(item.get("entry_id") or "")
                entry = models.find_entry(profile, key, eid) if eid else None
                if entry is None:
                    add(
                        "error",
                        "structure",
                        "%s 第 %d 条引用了主履历里不存在的条目（entry_id=%s）" % (title, ii + 1, eid or "空"),
                        path,
                    )
                    continue
                if not entry.get("confirmed", True):
                    add(
                        "warn",
                        "structure",
                        "%s 第 %d 条对应的是「待确认」履历条目，建议先确认" % (title, ii + 1),
                        path,
                    )
                source = (entry.get("org") or "") + " " + (entry.get("role") or "") + " " + (entry.get("raw") or "")
                bullets = item.get("bullets") or []
                if not bullets and key in ("work", "projects"):
                    add("warn", "quality", "%s 第 %d 条没有任何要点内容" % (title, ii + 1), path)
                for bi, b in enumerate(bullets):
                    text = b.get("text") if isinstance(b, dict) else b
                    check_text(
                        text,
                        "%s「%s」要点 %d" % (title, entry.get("org") or "", bi + 1),
                        source,
                        [key, ii, bi],
                    )
            else:
                for bi, b in enumerate(items):
                    text = b.get("text") if isinstance(b, dict) else b
                    label = "%s第 %d 条" % (title, bi + 1)
                    if key == "skills":
                        check_skill(text, label, [key, ii, bi])
                    else:
                        check_text(text, label, corpus, [key, ii, bi])
    return issues


def check_free_text_item(text: str, corpus: str, source_quotes, label: str,
                         max_chars: int = 260) -> list:
    """检查自由文本履历改写的一条内容及其原文证据。

    与结构化履历不同，这里没有 entry_id 可依赖，因此要求模型为每条事实
    内容提供逐句原文摘录；程序校验摘录必须真的出现在个人履历里，再叠加
    数字、技术名词和措辞升级检查。
    """
    issues = []
    text = str(text or "").strip()
    quotes = [str(q or "").strip() for q in (source_quotes or []) if str(q or "").strip()]
    corpus_norm = _norm(corpus)
    quote_norm = _norm(" ".join(quotes))
    corpus_tokens = {t.lower() for t in _en_tokens(corpus)}
    corpus_numbers = _numbers(corpus)
    allowed_years = allowed_year_counts_from_text(corpus)

    def add(level, kind, message):
        issues.append({"level": level, "kind": kind, "message": message, "path": []})

    if not text:
        add("error", "quality", "%s：内容为空" % label)
        return issues
    if len(text) > max_chars:
        add("warn", "quality", "%s：共 %d 字，偏长，建议精简" % (label, len(text)))
    if not quotes:
        add("error", "evidence", "%s：没有提供原文摘录，无法确认真实性" % label)
    for quote in quotes:
        qn = _norm(quote)
        if len(qn) < 4:
            add("error", "evidence", "%s：原文摘录过短「%s」" % (label, quote))
        elif qn not in corpus_norm:
            add("error", "evidence", "%s：原文摘录在个人履历中找不到「%s」" % (label, quote))

    for match in _NUM_RE.finditer(text):
        number = _canon_num(match.group(0))
        if number not in corpus_numbers:
            if text[match.end():].lstrip().startswith("年") and number in allowed_years:
                continue
            add("error", "number", "%s：出现个人履历中查不到的数字「%s」" % (label, number))
    for token in sorted(_en_tokens(text)):
        low = token.lower()
        if len(low) < 2 or low in _EN_STOPWORDS or low in corpus_tokens:
            continue
        add("warn", "entity", "%s：出现个人履历中没有的技术名词「%s」，请确认" % (label, token))
    for term in sorted(_quoted_terms(text)):
        if _norm(term) and _norm(term) not in corpus_norm:
            add("warn", "entity", "%s：出现个人履历中没有的术语「%s」" % (label, term))

    support = quote_norm or corpus_norm
    for word, supports in _SUPPORT_OF.items():
        if word in text and word not in support and not any(s in support for s in supports):
            add("warn", "wording", "%s：使用了「%s」，但原文摘录里缺少支撑" % (label, word))
    return issues


def blocking(issues) -> list:
    return [i for i in issues if i.get("level") == "error"]


def warnings(issues) -> list:
    return [i for i in issues if i.get("level") == "warn"]


def format_report(issues, limit: int = 40) -> str:
    if not issues:
        return "未发现真实性问题。"
    lines = []
    for i in issues[:limit]:
        mark = "×" if i.get("level") == "error" else "!"
        lines.append("%s [%s] %s" % (mark, i.get("kind", ""), i.get("message", "")))
    if len(issues) > limit:
        lines.append("… 另有 %d 条" % (len(issues) - limit))
    return "\n".join(lines)


def flag_document(doc: dict, issues) -> None:
    """把违规位置在文档里打上 flagged 标记（界面标红 / 标黄用）。"""
    for issue in issues:
        path = issue.get("path") or []
        if not path:
            continue
        if path[0] == "summary":
            doc["summary_flagged"] = issue.get("level") == "error"
            continue
        key, ii = path[0], path[1] if len(path) > 1 else -1
        for sec in doc.get("sections") or []:
            if sec.get("key") != key:
                continue
            items = sec.get("items") or []
            if not (0 <= ii < len(items)):
                continue
            item = items[ii]
            if len(path) >= 3:
                bullets = item.get("bullets")
                if key == "skills" or bullets is None:
                    item["flagged"] = True
                    continue
                bi = path[2]
                if 0 <= bi < len(bullets):
                    bullets[bi]["flagged"] = True
            else:
                item["flagged"] = True
