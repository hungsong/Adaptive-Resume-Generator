# -*- coding: utf-8 -*-
"""生成复用预检、表达强度签名与仅隐藏当前列表。"""
import pytest

from core import intent, jobs, tailor_text


def _current_job(profile: str, criteria: dict) -> dict:
    normalized = intent.normalize_criteria(criteria)
    return {
        "id": "job-1",
        "jd_hash": "jd-1",
        "tailored": {
            "text": "已有的当前文字简历",
            "status": "ok",
            "jd_hash": "jd-1",
            "profile_hash": tailor_text.profile_hash(profile),
            "criteria_hash": intent.criteria_signature(normalized),
            "strength": normalized["rewrite_strength"],
        },
    }


def test_rewrite_strength_changes_signature_and_invalidates_reuse():
    profile = "完整的个人履历正文" * 20
    standard = intent.normalize_criteria({"directions": ["视觉"], "rewrite_strength": "standard"})
    precise = intent.normalize_criteria({"directions": ["视觉"], "rewrite_strength": "precise"})
    assert intent.criteria_signature(standard) != intent.criteria_signature(precise)

    job = _current_job(profile, standard)
    assert tailor_text.result_is_current(job, profile, standard) is True
    assert tailor_text.result_is_current(job, profile, precise) is False
    report = tailor_text.preflight_jobs([job], profile, precise)
    assert len(report["stale"]) == 1
    assert report["model_calls_needed"] == 1


def test_preflight_classifies_without_calling_model():
    profile = "完整的个人履历正文" * 20
    criteria = {"directions": ["视觉"], "rewrite_strength": "standard"}
    current = _current_job(profile, criteria)
    stale = dict(current, id="job-2")
    stale["tailored"] = dict(current["tailored"], profile_hash="old-profile")
    missing = {"id": "job-3", "jd_hash": "jd-3", "tailored": {}}

    report = tailor_text.preflight_jobs([current, stale, missing], profile, criteria)
    assert [item["id"] for item in report["reusable"]] == ["job-1"]
    assert [item["id"] for item in report["stale"]] == ["job-2"]
    assert [item["id"] for item in report["missing"]] == ["job-3"]
    assert report["model_calls_needed"] == 2


def test_clear_current_list_only_hides_jobs(tmp_path, monkeypatch):
    pool = tmp_path / "jobs.json"
    hidden = tmp_path / "hidden.json"
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", pool)
    monkeypatch.setattr(jobs, "HIDDEN_JOBS_PATH", hidden)
    jobs.save_pool([{"id": "job-a", "title": "A"}, {"id": "job-b", "title": "B"}])

    jobs.hide_jobs(["job-a"])
    assert jobs.load_hidden() == {"job-a"}
    assert {job["id"] for job in jobs.load_pool()} == {"job-a", "job-b"}

    jobs.unhide_all()
    assert jobs.load_hidden() == set()
    assert {job["id"] for job in jobs.load_pool()} == {"job-a", "job-b"}

