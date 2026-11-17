# -*- coding: utf-8 -*-
"""浏览器实时岗位：单岗评分、自动改写与 SQLite 契约测试。"""
import pytest

from core import job_db, jobs, live, store


PROFILE = """张三，机器视觉工程师，现居苏州。
2020.03-2023.05 在示例自动化担任视觉工程师，负责客户现场设备调试。
使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯。
独立完成 12 个项目的视觉方案选型。"""


class FakeLLM:
    model = "fake-model"

    def __init__(self, score=92, fail_score=False):
        self.score = score
        self.fail_score = fail_score
        self.calls = 0

    def complete_json(self, system, user, **kwargs):
        self.calls += 1
        if "岗位意向匹配评估器" in system:
            if self.fail_score:
                raise RuntimeError("模拟评分失败")
            return {
                "direction": {"score": self.score, "reason": "方向匹配"},
                "responsibilities": {"score": self.score, "reason": "职责匹配"},
                "industry": {"score": self.score, "reason": "行业相关"},
                "salary": {"score": self.score, "reason": "薪资匹配"},
                "level_company": {"score": self.score, "reason": "职级合适"},
                "summary": "推荐投递",
                "risks": [],
            }
        return {
            "job_summary": "重视机器视觉现场调试",
            "requirements": [{
                "requirement": "机器视觉现场调试", "type": "核心", "status": "covered",
                "source_quote": "使用机器视觉系统完成客户现场设备调试", "note": "",
            }],
            "sections": [{
                "title": "工作经历",
                "items": [{
                    "text": "使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯。",
                    "source_quotes": [
                        "使用机器视觉系统完成客户现场设备调试",
                        "涉及相机、光源、PLC、TCP/IP 通讯",
                    ],
                }],
            }],
            "editor_notes": [],
        }


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    pool = tmp_path / "jobs.json"
    backup = tmp_path / "backup"
    backup.mkdir()
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", pool)
    monkeypatch.setattr(store, "BACKUP_DIR", backup)
    monkeypatch.setattr(job_db, "JOB_DB_PATH", tmp_path / "jobs.db")
    return tmp_path


def _job(url="https://www.zhipin.com/job_detail/live1.html"):
    return {
        "job_id": "live1", "url": url, "title": "机器视觉工程师",
        "company": "示例公司", "city": "苏州", "salary": "20-30K",
        "experience": "3-5年", "education": "本科",
        "company_scale": "100-499人", "industry": "工业自动化",
        "jd_text": "负责机器视觉方案设计，使用相机、光源、PLC 与 TCP/IP 通讯，"
                   "完成客户现场调试和项目交付。岗位要求统招本科，三年以上经验。" * 2,
        "extension_score": 75, "scanned_at": "2026-10-25T10:00:00+08:00",
    }


def _criteria(**extra):
    data = {
        "directions": ["机器视觉"], "cities": ["苏州"], "salary_min": 15,
        "recommend_threshold": 78, "review_threshold": 62, "scan_limit": 30,
    }
    data.update(extra)
    return data


def test_live_recommended_job_is_scored_and_tailored(sandbox):
    result = live.process_live_job(_job(), _criteria(), PROFILE, FakeLLM())
    assert result["status"] == "recommended"
    assert result["score"] == 92
    assert result["tailored"] is True

    pool = jobs.load_pool()
    assert len(pool) == 1
    assert pool[0]["intent"]["status"] == "recommended"
    assert "使用机器视觉系统完成客户现场设备调试" in pool[0]["tailored"]["text"]

    summary = job_db.summary()
    assert summary == {"jobs": 1, "scores": 1, "resumes": 1, "scans": 0}


def test_live_review_job_is_not_auto_tailored(sandbox):
    result = live.process_live_job(_job(), _criteria(), PROFILE, FakeLLM(score=70))
    assert result["status"] == "review"
    assert result["tailored"] is False
    assert jobs.load_pool()[0]["tailored"] == {}


def test_live_duplicate_updates_single_record(sandbox):
    live.process_live_job(_job(), _criteria(), PROFILE, FakeLLM())
    job = _job()
    job["salary"] = "22-32K"
    live.process_live_job(job, _criteria(), PROFILE, FakeLLM(score=70))
    pool = jobs.load_pool()
    assert len(pool) == 1
    assert pool[0]["salary"] == "22-32K"


def test_live_score_failure_keeps_job_and_returns_error(sandbox):
    result = live.process_live_job(
        _job(), _criteria(), PROFILE, FakeLLM(fail_score=True)
    )
    assert result["status"] == "error"
    assert "模拟评分失败" in result["score_error"]
    pool = jobs.load_pool()
    assert len(pool) == 1
    assert pool[0]["intent"]["status"] == "error"


def test_live_short_jd_skips_model_calls(sandbox):
    llm = FakeLLM()
    job = _job()
    job["jd_text"] = "太短"
    result = live.process_live_job(job, _criteria(), PROFILE, llm, auto_tailor=True)
    assert result["status"] == "needs_detail"
    assert llm.calls == 0
