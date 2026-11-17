# -*- coding: utf-8 -*-
"""岗位池导入、去重与 JD 变更失效测试。"""
import json

import pytest

from core import jobs, store


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    pool = tmp_path / "jobs.json"
    backup = tmp_path / "backup"
    backup.mkdir()
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", pool)
    monkeypatch.setattr(store, "BACKUP_DIR", backup)
    return {"pool": pool, "backup": backup}


def _job(jd="负责机器视觉方案设计，使用相机、光源、PLC 与 TCP/IP 通讯，完成客户现场调试。", url="https://www.zhipin.com/job_detail/abc.html?x=1"):
    return {
        "job_id": "abc", "url": url, "title": "视觉工程师", "company": "示例公司",
        "city": "苏州", "salary": "20-30K", "experience": "3-5年",
        "education": "本科", "company_scale": "100-499人",
        "industry": "工业自动化", "jd_text": jd,
        "extension_score": 82, "extension_reason": "方向匹配",
        "extension_action": "favorite", "favorited": True,
    }


def test_import_normalized_and_legacy_formats(sandbox, tmp_path):
    normalized = tmp_path / "normalized.json"
    normalized.write_text(json.dumps({
        "schema_version": 1, "source": "boss", "jobs": [_job()],
    }, ensure_ascii=False), encoding="utf-8")
    report = jobs.import_file(normalized)
    assert report["added"] == 1
    pool = jobs.load_pool()
    assert pool[0]["title"] == "视觉工程师"
    assert pool[0]["url"] == "https://www.zhipin.com/job_detail/abc.html"
    assert pool[0]["company"] == "示例公司"
    assert pool[0]["city"] == "苏州"
    assert pool[0]["experience"] == "3-5年"
    assert pool[0]["education"] == "本科"
    assert pool[0]["company_scale"] == "100-499人"
    assert pool[0]["industry"] == "工业自动化"

    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"records": [{
        "title": "旧岗位", "href": "https://www.zhipin.com/job_detail/old.html",
        "detailText": "这是旧版记录里的完整岗位描述。" * 12,
        "score": 66, "action": "review", "time": "2026-10-01T00:00:00Z",
    }]}, ensure_ascii=False), encoding="utf-8")
    report = jobs.import_file(legacy)
    assert report["added"] == 1
    assert len(jobs.load_pool()) == 2


def test_duplicate_import_preserves_results(sandbox, tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [_job()]}, ensure_ascii=False), encoding="utf-8")
    jobs.import_file(path)
    pool = jobs.load_pool()
    pool[0]["intent"] = {"status": "recommended", "score": 88, "cache_key": "x"}
    pool[0]["tailored"] = {"text": "已生成的文字", "jd_hash": pool[0]["jd_hash"]}
    jobs.save_pool(pool)

    report = jobs.import_file(path)
    assert report["unchanged"] == 1
    kept = jobs.load_pool()[0]
    assert kept["intent"]["score"] == 88
    assert kept["tailored"]["text"] == "已生成的文字"


def test_jd_change_invalidates_old_results(sandbox, tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [_job()]}, ensure_ascii=False), encoding="utf-8")
    jobs.import_file(path)
    pool = jobs.load_pool()
    pool[0]["intent"] = {"status": "recommended", "score": 88}
    pool[0]["tailored"] = {"text": "旧文字", "jd_hash": pool[0]["jd_hash"]}
    jobs.save_pool(pool)

    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps({"jobs": [_job(jd="岗位要求已经完全改变。" * 20)]}, ensure_ascii=False), encoding="utf-8")
    report = jobs.import_file(changed)
    assert report["jd_changed"] == 1
    updated = jobs.load_pool()[0]
    assert updated["intent"] == {}
    assert updated["tailored"] == {}


def test_short_jd_is_flagged(sandbox):
    merged, report = jobs.merge_jobs([], [{
        "url": "https://www.zhipin.com/job_detail/short.html",
        "title": "短 JD", "jd_text": "太短",
    }])
    assert report["short_jd"] == 1
    assert merged[0]["usability"] == "short_jd"
