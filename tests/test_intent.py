# -*- coding: utf-8 -*-
"""意向门槛、薪资解析与双阈值评分测试。"""
from core import intent


class FakeLLM:
    model = "fake-model"

    def __init__(self, score=90):
        self.score = score
        self.calls = 0

    def complete_json(self, *args, **kwargs):
        self.calls += 1
        return {
            "direction": {"score": self.score, "reason": "方向一致"},
            "responsibilities": {"score": self.score, "reason": "职责一致"},
            "industry": {"score": self.score, "reason": "行业相关"},
            "salary": {"score": self.score, "reason": "薪资匹配"},
            "level_company": {"score": self.score, "reason": "职级合适"},
            "summary": "值得投递",
            "risks": [],
        }


def _job(jd=None, **extra):
    data = {
        "title": "机器视觉工程师", "company": "示例公司", "city": "苏州",
        "salary": "20-30K",
        "jd_text": jd or ("负责机器视觉方案设计，使用相机、光源、PLC 与 TCP/IP 通讯，"
                         "完成客户现场调试和项目交付。岗位要求统招本科，三年以上经验。" * 2),
        "jd_hash": "h1", "extension_score": 80,
    }
    data.update(extra)
    return data


def _criteria(**extra):
    data = {"directions": ["机器视觉"], "cities": ["苏州"], "salary_min": 15,
            "recommend_threshold": 78, "review_threshold": 62}
    data.update(extra)
    return intent.normalize_criteria(data)


def test_salary_parsing():
    assert intent.parse_salary_range("20-30K·14薪") == (20.0, 30.0)
    low, high = intent.parse_salary_range("20-30万/年")
    assert 15 < low < 18 and 24 < high < 26


def test_city_alias_is_normalized_and_matches_boss_city():
    criteria = _criteria(cities=["NingBo"])
    assert criteria["cities"] == ["宁波"]
    gate = intent.local_gate(_job(city="宁波"), criteria)
    assert gate["passed"] is True


def test_local_gate_rejects_excluded_word():
    gate = intent.local_gate(_job(), _criteria(exclude_words=["PLC"]))
    assert gate["passed"] is False
    assert any("排除词" in reason for reason in gate["reasons"])


def test_high_score_is_recommended():
    result = intent.judge_job(_job(), _criteria(), FakeLLM(90))
    assert result["status"] == "recommended"
    assert result["score"] == 90


def test_middle_score_is_review_and_low_score_is_rejected():
    review = intent.judge_job(_job(), _criteria(), FakeLLM(70))
    assert review["status"] == "review"
    rejected = intent.judge_job(_job(), _criteria(), FakeLLM(40))
    assert rejected["status"] == "rejected"


def test_short_jd_needs_detail_without_llm_call():
    llm = FakeLLM()
    result = intent.judge_job(_job(jd="太短"), _criteria(), llm)
    assert result["status"] == "needs_detail"
    assert llm.calls == 0


def test_cache_avoids_second_call():
    llm = FakeLLM(90)
    job = _job()
    first = intent.judge_job(job, _criteria(), llm)
    job["intent"] = first
    second = intent.judge_job(job, _criteria(), llm)
    assert second["score"] == first["score"]
    assert llm.calls == 1
