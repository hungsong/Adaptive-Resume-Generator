# -*- coding: utf-8 -*-
"""自由文本改写：证据逐句校验、数字拦截与带反馈重试。"""
from core import tailor_text

PROFILE = """张三，机器视觉工程师，现居苏州。
工作经历：2020.03-2023.05 在示例自动化担任视觉工程师，负责客户现场设备调试。
使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯。
独立完成 12 个项目的视觉方案选型。
技能：机器视觉、PLC、C#。"""


class FakeLLM:
    model = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete_json(self, *args, **kwargs):
        self.calls += 1
        return self.replies.pop(0)


def _payload(text="使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯。",
             quotes=None):
    return {
        "job_summary": "重视现场视觉调试",
        "requirements": [
            {"requirement": "机器视觉现场调试", "type": "核心", "status": "covered",
             "source_quote": "使用机器视觉系统完成客户现场设备调试", "note": ""},
        ],
        "sections": [{"title": "工作经历", "items": [{
            "text": text,
            "source_quotes": quotes if quotes is not None else [
                "使用机器视觉系统完成客户现场设备调试",
                "涉及相机、光源、PLC、TCP/IP 通讯",
            ],
        }]}],
        "editor_notes": [],
    }


def test_valid_result_passes_and_builds_text():
    sections, requirements, issues = tailor_text.validate_result(_payload(), PROFILE)
    assert sections and requirements
    assert [i for i in issues if i["level"] == "error"] == []
    text = tailor_text.build_plain_text(sections)
    assert text.startswith("工作经历")
    assert "TCP/IP" in text


def test_missing_quote_is_blocked():
    _, _, issues = tailor_text.validate_result(_payload(quotes=[]), PROFILE)
    assert any(i["kind"] == "evidence" and i["level"] == "error" for i in issues)


def test_quote_not_in_profile_is_blocked():
    _, _, issues = tailor_text.validate_result(_payload(quotes=["这句话不在履历里"]), PROFILE)
    assert any(i["kind"] == "evidence" and i["level"] == "error" for i in issues)


def test_fabricated_number_is_blocked():
    _, _, issues = tailor_text.validate_result(
        _payload(text="使用机器视觉系统完成客户现场设备调试，效率提升 30%。"), PROFILE
    )
    assert any(i["kind"] == "number" and i["level"] == "error" for i in issues)


def test_years_inferred_from_date_range_are_allowed():
    profile = "工作经历：2020-2023 在示例自动化担任视觉工程师。\n负责客户现场设备调试。"
    payload = {
        "sections": [{"title": "个人简介", "items": [{
            "text": "拥有 3 年机器视觉现场调试经验。",
            "source_quotes": ["负责客户现场设备调试"],
        }]}],
    }
    _, _, issues = tailor_text.validate_result(payload, profile)
    assert not [i for i in issues if i["kind"] == "number" and i["level"] == "error"]


def test_retry_receives_feedback_and_can_recover():
    llm = FakeLLM([_payload(quotes=[]), _payload()])
    result = tailor_text.tailor_job(
        {"title": "视觉工程师", "jd_hash": "h1"}, PROFILE, {"criteria_hash": "c1"}, llm
    )
    assert llm.calls == 2
    assert result["attempts"] == 2
    assert result["status"] == "ok"
