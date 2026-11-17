# -*- coding: utf-8 -*-
"""端到端流水线测试：导入 -> 评分 -> 达标 -> 文字改写 -> 落盘。"""
import json

import pytest

from core import jobs, pipeline, store


PROFILE = """张三，机器视觉工程师，现居苏州。
2020.03-2023.05 在示例自动化担任视觉工程师，负责客户现场设备调试。
使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯。
独立完成 12 个项目的视觉方案选型。"""


class FakeLLM:
    model = "fake-model"

    def complete_json(self, system, user, **kwargs):
        if "岗位意向匹配评估器" in system:
            return {
                "direction": {"score": 92, "reason": "方向匹配"},
                "responsibilities": {"score": 88, "reason": "职责匹配"},
                "industry": {"score": 80, "reason": "行业相关"},
                "salary": {"score": 85, "reason": "薪资匹配"},
                "level_company": {"score": 82, "reason": "职级合适"},
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
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"jobs": [{
        "url": "https://www.zhipin.com/job_detail/abc.html",
        "title": "机器视觉工程师", "company": "示例公司", "city": "苏州",
        "salary": "20-30K",
        "jd_text": "负责机器视觉方案设计，使用相机、光源、PLC 与 TCP/IP 通讯，"
                   "完成客户现场调试和项目交付。岗位要求统招本科，三年以上经验。" * 2,
    }]}, ensure_ascii=False), encoding="utf-8")
    jobs.import_file(source)
    return pool


def test_full_pipeline_persists_tailored_text(sandbox):
    criteria = {
        "directions": ["机器视觉"], "cities": ["苏州"], "salary_min": 15,
        "recommend_threshold": 78, "review_threshold": 62, "max_tailor_per_run": 5,
    }
    progress = []
    report = pipeline.run_batch(
        criteria, PROFILE, FakeLLM(), progress=lambda p, m: progress.append((p, m)),
        mode="all",
    )
    assert report["scored"] == 1
    assert report["recommended"] == 1
    assert report["tailored"] == 1
    assert progress and progress[-1][0] == 100

    pool = jobs.load_pool()
    assert pool[0]["intent"]["status"] == "recommended"
    tailored = pool[0]["tailored"]
    assert tailored["status"] == "ok"
    assert "使用机器视觉系统完成客户现场设备调试" in tailored["text"]


def test_only_recommended_jobs_are_tailored(sandbox):
    criteria = {
        "directions": ["机器视觉"], "recommend_threshold": 101, "review_threshold": 0,
        "max_tailor_per_run": 5,
    }
    # normalize 会把 101 收回到 100；仍用低分模型走 review，不应自动改写。
    class LowLLM(FakeLLM):
        def complete_json(self, system, user, **kwargs):
            data = super().complete_json(system, user, **kwargs)
            if "岗位意向匹配评估器" in system:
                for key in ("direction", "responsibilities", "industry", "salary", "level_company"):
                    data[key]["score"] = 70
            return data

    report = pipeline.run_batch(criteria, PROFILE, LowLLM(), mode="all")
    assert report["review"] == 1
    assert report["tailored"] == 0
