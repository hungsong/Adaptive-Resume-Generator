# -*- coding: utf-8 -*-
"""自由文本履历的保存与旧数据迁移测试。"""
from core import models, profile_text, store


def _sandbox(tmp_path, monkeypatch):
    target = tmp_path / "profile_text.json"
    legacy = tmp_path / "profile.json"
    backup = tmp_path / "backup"
    backup.mkdir()
    monkeypatch.setattr(profile_text, "PROFILE_TEXT_PATH", target)
    monkeypatch.setattr(store, "PROFILE_PATH", legacy)
    monkeypatch.setattr(store, "BACKUP_DIR", backup)
    return target, legacy


def test_roundtrip(tmp_path, monkeypatch):
    target, _ = _sandbox(tmp_path, monkeypatch)
    profile_text.save_profile_text("完整履历第一版")
    loaded = profile_text.load_profile_text()
    assert loaded["text"] == "完整履历第一版"
    assert loaded["updated_at"]
    profile_text.save_profile_text("完整履历第二版")
    assert profile_text.load_profile_text()["text"] == "完整履历第二版"
    assert target.exists()


def test_migrates_structured_profile_without_deleting_it(tmp_path, monkeypatch):
    _, legacy = _sandbox(tmp_path, monkeypatch)
    prof = models.normalize_profile({
        "personal": {"name": "张三", "city": "苏州"},
        "sections": {"work": [{"org": "示例公司", "role": "视觉工程师",
                               "start": "2020.03", "end": "2023.05",
                               "raw": "完成现场相机调试", "confirmed": True}]},
    })
    legacy.write_text(__import__("json").dumps(prof, ensure_ascii=False), encoding="utf-8")
    loaded = profile_text.load_profile_text()
    assert "张三" in loaded["text"]
    assert "示例公司" in loaded["text"]
    assert "完成现场相机调试" in loaded["text"]
    assert loaded["migrated_from"].endswith("profile.json")
    assert legacy.exists()
