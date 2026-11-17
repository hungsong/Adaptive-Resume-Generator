# -*- coding: utf-8 -*-
"""Local-data reset guard and irreversible-action confirmation."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt5.QtWidgets import QApplication

from core.data_reset import clear_local_data
from ui.data_reset_dialog import ClearDataDialog
from ui import page_settings as settings_module


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seed_app_dir(root):
    (root / "data" / "profiles" / "role-a").mkdir(parents=True)
    (root / "data" / "profiles" / "role-a" / "profile_text.json").write_text(
        '{"text": "私人履历"}', encoding="utf-8"
    )
    (root / "logs").mkdir()
    (root / "logs" / "app.log").write_text("private log", encoding="utf-8")
    (root / "config.json").write_text('{"api": {"api_key": "test-only"}}', encoding="utf-8")
    (root / "main.py").write_text("# app", encoding="utf-8")


def test_clear_local_data_keeps_api_config_by_default(tmp_path):
    _seed_app_dir(tmp_path)

    report = clear_local_data(app_dir=tmp_path)

    assert report["failures"] == []
    assert report["removed"] == ["data", "logs"]
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "logs").exists()
    assert (tmp_path / "config.json").exists()
    assert "test-only" in (tmp_path / "config.json").read_text(encoding="utf-8")
    assert (tmp_path / "main.py").exists()


def test_clear_local_data_can_remove_config_when_explicit(tmp_path):
    _seed_app_dir(tmp_path)

    report = clear_local_data(include_config=True, app_dir=tmp_path)

    assert report["failures"] == []
    assert report["removed"] == ["data", "logs", "config.json"]
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "config.json").exists()


def test_clear_local_data_reports_missing_targets_without_touching_app(tmp_path):
    report = clear_local_data(app_dir=tmp_path)

    assert report["removed"] == []
    assert report["missing"] == ["data", "logs"]
    assert report["failures"] == []


def test_dialog_requires_exact_confirmation_word(app):
    dialog = ClearDataDialog()

    assert not dialog.btn_clear.isEnabled()
    dialog.confirm_edit.setText("清除")
    assert not dialog.btn_clear.isEnabled()
    dialog.confirm_edit.setText("  清空  ")
    assert dialog.btn_clear.isEnabled()
    dialog.include_config.setChecked(True)
    assert dialog.delete_config_requested() is True
    dialog.deleteLater()


def test_settings_clear_button_emits_reset_request(app, monkeypatch):
    cfg = {"api": {}, "ui": {"theme": "light"}}
    api = {
        "base_url": "https://api.example.com",
        "model": "example-model",
        "api_key": "",
        "timeout": 120,
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    monkeypatch.setattr(settings_module, "load_config", lambda: cfg)
    monkeypatch.setattr(settings_module, "api_config", lambda _cfg: dict(api))
    monkeypatch.setattr(settings_module.profiles, "active_profile", lambda: None)
    monkeypatch.setattr(
        settings_module, "detect_browsers",
        lambda: [{"key": "system", "name": "系统默认浏览器", "path": ""}],
    )

    page = settings_module.SettingsPage(None)
    fired = []
    page.clear_data_requested.connect(lambda: fired.append(True))
    page.btn_clear_data.click()

    assert fired == [True]
    page.deleteLater()
