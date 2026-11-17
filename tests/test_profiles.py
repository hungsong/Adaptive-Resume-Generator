# -*- coding: utf-8 -*-
"""角色工作区：创建、切换、路径隔离，以及旧数据复制而不迁移。"""
import json

import pytest

from core import config, intent, job_db, jobs, profile_text, profiles, store


@pytest.fixture()
def profile_env(tmp_path, monkeypatch):
    root = tmp_path / "data"
    legacy_jobs = root / "jobs"
    legacy_jobs.mkdir(parents=True)
    (root / "backup").mkdir()
    (root / "versions").mkdir()

    (root / "profile_text.json").write_text(json.dumps({
        "schema_version": 1, "text": "旧角色履历正文" * 20, "source_file": "",
    }, ensure_ascii=False), encoding="utf-8")
    (root / "profile.json").write_text('{"personal": {"name": "旧角色"}}', encoding="utf-8")
    (root / "intent.json").write_text(json.dumps({"directions": ["视觉"]}), encoding="utf-8")
    (legacy_jobs / "jobs.json").write_text(json.dumps({"jobs": [{"id": "old"}]}), encoding="utf-8")
    (root / "jobs.db").write_bytes(b"legacy-sqlite-placeholder")

    monkeypatch.setattr(config, "PROFILES_DIR", root / "profiles")
    monkeypatch.setattr(config, "PROFILES_INDEX_PATH", root / "profiles" / "profiles.json")
    monkeypatch.setattr(config, "PROFILE_TEXT_PATH", root / "profile_text.json")
    monkeypatch.setattr(config, "PROFILE_PATH", root / "profile.json")
    monkeypatch.setattr(config, "INTENT_PATH", root / "intent.json")
    monkeypatch.setattr(config, "JOBS_DIR", legacy_jobs)
    monkeypatch.setattr(config, "JOB_POOL_PATH", legacy_jobs / "jobs.json")
    monkeypatch.setattr(config, "JOB_DB_PATH", root / "jobs.db")
    monkeypatch.setattr(config, "HIDDEN_JOBS_PATH", legacy_jobs / "hidden.json")
    monkeypatch.setattr(config, "BACKUP_DIR", root / "backup")
    monkeypatch.setattr(config, "VERSIONS_DIR", root / "versions")

    monkeypatch.setattr(store, "PROFILE_PATH", root / "profile.json")
    monkeypatch.setattr(store, "BACKUP_DIR", root / "backup")
    monkeypatch.setattr(store, "VERSIONS_DIR", root / "versions")
    monkeypatch.setattr(profile_text, "PROFILE_TEXT_PATH", root / "profile_text.json")
    monkeypatch.setattr(intent, "INTENT_PATH", root / "intent.json")
    monkeypatch.setattr(intent, "PROFILE_PATH", root / "profile.json")
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", legacy_jobs / "jobs.json")
    monkeypatch.setattr(jobs, "HIDDEN_JOBS_PATH", legacy_jobs / "hidden.json")
    monkeypatch.setattr(job_db, "JOB_DB_PATH", root / "jobs.db")
    return root


def test_adopt_legacy_copies_everything_and_keeps_originals(profile_env):
    root = profile_env
    assert profiles.legacy_available() is True

    first = profiles.create_profile("旧数据角色", adopt_legacy=True)
    paths = profiles.profile_paths(first["id"])
    assert profiles.active_profile()["id"] == first["id"]
    assert paths["profile_text"].exists()
    assert paths["jobs"].exists()
    assert paths["jobs_db"].read_bytes() == b"legacy-sqlite-placeholder"

    assert (root / "profile_text.json").exists()
    assert (root / "jobs.db").exists()
    assert (root / "jobs" / "jobs.json").exists()


def test_switching_profiles_updates_all_module_paths_and_isolates_data(profile_env):
    first = profiles.create_profile("角色一", initial_text="角色一的完整履历。" * 20)
    second = profiles.create_profile("角色二", initial_text="角色二完全不同的履历。" * 20)
    first_paths = profiles.profile_paths(first["id"])
    second_paths = profiles.profile_paths(second["id"])

    assert config.PROFILE_TEXT_PATH == second_paths["profile_text"]
    assert jobs.JOB_POOL_PATH == second_paths["jobs"]
    assert job_db.JOB_DB_PATH == second_paths["jobs_db"]

    profiles.activate_profile(first["id"])
    assert config.PROFILE_TEXT_PATH == first_paths["profile_text"]
    assert jobs.JOB_POOL_PATH == first_paths["jobs"]
    assert jobs.HIDDEN_JOBS_PATH == first_paths["hidden"]
    assert job_db.JOB_DB_PATH == first_paths["jobs_db"]
    assert profiles.load_registry()["active_id"] == first["id"]
    assert "角色一的完整履历" in profile_text.load_profile_text()["text"]
    assert not second_paths["jobs"].exists() or json.loads(
        second_paths["jobs"].read_text(encoding="utf-8")
    ).get("jobs") == []


def test_clear_active_requires_new_role_selection(profile_env):
    record = profiles.create_profile("可切换角色")
    assert profiles.active_profile()["id"] == record["id"]
    profiles.clear_active()
    assert profiles.active_profile() is None


def test_delete_inactive_profile_removes_only_its_workspace(profile_env):
    first = profiles.create_profile("待删除角色", initial_text="待删除角色的履历。" * 20)
    second = profiles.create_profile("保留角色", initial_text="保留角色的履历。" * 20)
    first_paths = profiles.profile_paths(first["id"])
    second_paths = profiles.profile_paths(second["id"])
    first_paths["jobs_db"].write_bytes(b"role-local-db")
    assert first_paths["base"].exists()

    deleted = profiles.delete_profile(first["id"])

    assert deleted["id"] == first["id"]
    assert profiles.get_profile(first["id"]) is None
    assert profiles.active_profile()["id"] == second["id"]
    assert not first_paths["base"].exists()
    assert second_paths["base"].exists()
    assert "保留角色的履历" in profile_text.load_profile_text()["text"]


def test_delete_active_profile_is_rejected(profile_env):
    record = profiles.create_profile("当前角色", initial_text="当前角色履历。" * 20)
    paths = profiles.profile_paths(record["id"])

    with pytest.raises(ValueError, match="当前角色不能直接删除"):
        profiles.delete_profile(record["id"])

    assert profiles.get_profile(record["id"]) is not None
    assert profiles.active_profile()["id"] == record["id"]
    assert paths["base"].exists()

