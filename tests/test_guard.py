# -*- coding: utf-8 -*-
"""真实性校验测试：这是本项目的底线，必须能抓住虚构内容。"""
from core import guard, models

PROFILE = models.normalize_profile({
    "personal": {"name": "张三", "phone": "13800000000", "email": "a@b.com", "city": "苏州",
                 "target": "机器视觉工程师", "links": "github.com/zhangsan", "note": ""},
    "sections": {
        "work": [{"id": "w1", "org": "某某自动化", "role": "视觉工程师",
                  "start": "2020.03", "end": "2023.05",
                  "raw": "使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯\n独立完成 12 个项目的视觉方案选型",
                  "confirmed": True}],
        "skills": [{"id": "s1", "text": "机器视觉", "confirmed": True},
                   {"id": "s2", "text": "PLC", "confirmed": True}],
    },
})


def _doc(bullets, section="work"):
    item = {"entry_id": "w1", "org": "某某自动化", "role": "视觉工程师",
            "start": "2020.03", "end": "2023.05",
            "bullets": [{"text": b, "evidence_ids": ["w1"], "flagged": False} for b in bullets]}
    return {"summary": "3 年机器视觉现场调试经验。", "sections": [{"key": section, "title": "工作经历", "items": [item]}]}


def test_clean_resume_has_no_blocking_issue():
    issues = guard.check_resume(_doc(["使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯"]), PROFILE)
    assert guard.blocking(issues) == []


def test_fabricated_number_is_blocked():
    issues = guard.check_resume(_doc(["完成视觉方案调试，效率提升 30%"]), PROFILE)
    kinds = {i["kind"] for i in guard.blocking(issues)}
    assert "number" in kinds


def test_invented_skill_is_blocked():
    doc = {"summary": "", "sections": [{"key": "skills", "title": "技能", "items": [
        {"text": "C++", "evidence_ids": [], "flagged": False},
    ]}]}
    issues = guard.check_resume(doc, PROFILE)
    assert any(i["kind"] == "skill" and i["level"] == "error" for i in issues)


def test_unknown_entry_id_is_blocked():
    doc = _doc(["任意内容"])
    doc["sections"][0]["items"][0]["entry_id"] = "w99"
    issues = guard.check_resume(doc, PROFILE)
    assert any(i["kind"] == "structure" and i["level"] == "error" for i in issues)


def test_upgraded_wording_is_flagged():
    issues = guard.check_resume(_doc(["负责整条产线的视觉系统方案设计"]), PROFILE)
    assert any(i["kind"] == "wording" for i in issues)


def test_unconfirmed_entry_warns():
    profile = models.normalize_profile({
        "sections": {"work": [{"id": "w1", "org": "A", "role": "B", "start": "", "end": "",
                               "raw": "做了一些事", "confirmed": False}]}
    })
    doc = {"summary": "", "sections": [{"key": "work", "title": "工作经历", "items": [
        {"entry_id": "w1", "org": "A", "role": "B", "start": "", "end": "",
         "bullets": [{"text": "做了一些事", "evidence_ids": ["w1"], "flagged": False}]}]}]}
    issues = guard.check_resume(doc, profile)
    assert any(i["kind"] == "structure" and i["level"] == "warn" for i in issues)


def test_flag_document_marks_bullets():
    doc = _doc(["完成视觉方案调试，效率提升 30%"])
    issues = guard.check_resume(doc, PROFILE)
    guard.flag_document(doc, issues)
    assert doc["sections"][0]["items"][0]["bullets"][0]["flagged"] is True


def test_profile_corpus_keeps_real_newlines():
    """语料必须用真实换行拼接，否则英文技术词会被粘成一个词，导致误报。"""
    prof = models.normalize_profile({"sections": {"skills": [{"text": "C#（了解）"}]}})
    corpus = models.profile_corpus(prof)
    assert "\n" in corpus
    issues = guard.check_resume({"summary": "了解 C#，可配合完成联调。", "sections": []}, prof)
    assert not [i for i in issues if i["kind"] == "entity"]
