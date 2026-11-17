# -*- coding: utf-8 -*-
"""存储测试：原子写入、自动备份、版本增删查。"""
import json
from pathlib import Path

import pytest

from core import models, store


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "data"
    versions = data / "versions"
    backup = data / "backup"
    versions.mkdir(parents=True)
    backup.mkdir(parents=True)
    monkeypatch.setattr(store, "PROFILE_PATH", data / "profile.json")
    monkeypatch.setattr(store, "VERSIONS_DIR", versions)
    monkeypatch.setattr(store, "BACKUP_DIR", backup)
    return {"data": data, "versions": versions, "backup": backup}


def test_profile_roundtrip(sandbox):
    prof = models.normalize_profile({"personal": {"name": "张三"},
                                     "sections": {"skills": [{"text": "PLC"}]}})
    store.save_profile(prof)
    loaded = store.load_profile()
    assert loaded["personal"]["name"] == "张三"
    assert loaded["sections"]["skills"][0]["text"] == "PLC"
    assert loaded["sections"]["skills"][0]["id"] == "s1"
    assert store.profile_hash(loaded) == store.profile_hash(prof)


def test_backup_created_on_second_save(sandbox):
    prof = models.normalize_profile({"personal": {"name": "张三"}})
    store.save_profile(prof)
    prof["personal"]["name"] = "李四"
    store.save_profile(prof)
    assert len(list(sandbox["backup"].glob("profile-*.json"))) == 1


def test_version_lifecycle(sandbox):
    doc = models.empty_resume_doc("basic", "基础简历")
    doc["summary"] = "简介"
    vid = store.save_version(doc)
    assert vid and (sandbox["versions"] / ("%s.json" % vid)).exists()
    listed = store.list_versions()
    assert listed and listed[0]["id"] == vid
    assert store.load_version(vid)["summary"] == "简介"
    assert store.delete_version(vid) is True
    assert store.list_versions() == []


def test_version_ids_are_unique(sandbox):
    a = models.empty_resume_doc("basic", "A")
    b = models.empty_resume_doc("basic", "B")
    assert store.save_version(a) != store.save_version(b)
