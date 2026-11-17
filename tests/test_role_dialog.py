# -*- coding: utf-8 -*-
"""角色管理弹窗：当前角色保护、名称确认与删除调用。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from core import profiles
from ui.profile_dialogs import RoleDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _fake_profiles(monkeypatch):
    items = [
        {"id": "role-a", "name": "Alpha", "source": "blank"},
        {"id": "role-b", "name": "Beta", "source": "resume"},
    ]
    active = {"id": "role-b"}
    deleted = []

    monkeypatch.setattr(profiles, "list_profiles", lambda: list(items))
    monkeypatch.setattr(profiles, "active_profile", lambda: active)
    monkeypatch.setattr(
        profiles, "get_profile",
        lambda profile_id: next((p for p in items if p["id"] == profile_id), None),
    )
    monkeypatch.setattr(profiles, "legacy_available", lambda: False)

    def fake_delete(profile_id):
        record = next((p for p in items if p["id"] == profile_id), None)
        if not record:
            raise ValueError("角色不存在")
        deleted.append(profile_id)
        items[:] = [p for p in items if p["id"] != profile_id]
        return record

    monkeypatch.setattr(profiles, "delete_profile", fake_delete)
    return items, deleted


def _row_for(dialog, profile_id):
    for row in range(dialog.list.count()):
        item = dialog.list.item(row)
        if item.data(Qt.UserRole) == profile_id:
            return row
    return -1


def test_current_role_cannot_be_deleted_but_inactive_role_can(app, monkeypatch):
    items, deleted = _fake_profiles(monkeypatch)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: messages.append(args[1]))

    dialog = RoleDialog(startup=False)
    assert dialog.list.count() == 2
    assert dialog.list.currentItem().data(Qt.UserRole) == "role-b"
    assert not dialog.btn_delete.isEnabled()

    dialog.list.setCurrentRow(_row_for(dialog, "role-a"))
    assert dialog.btn_delete.isEnabled()

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Alpha", True))
    dialog._delete_selected()

    assert deleted == ["role-a"]
    assert [p["id"] for p in items] == ["role-b"]
    assert dialog.list.count() == 1
    assert dialog.list.currentItem().data(Qt.UserRole) == "role-b"
    assert not dialog.btn_delete.isEnabled()
    assert "角色已删除" in messages
    dialog.deleteLater()


def test_wrong_role_name_cancels_deletion(app, monkeypatch):
    _items, deleted = _fake_profiles(monkeypatch)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("alpha", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    dialog = RoleDialog(startup=False)
    dialog.list.setCurrentRow(_row_for(dialog, "role-a"))
    dialog._delete_selected()

    assert deleted == []
    assert dialog.list.count() == 2
    dialog.deleteLater()
