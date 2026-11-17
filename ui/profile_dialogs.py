# -*- coding: utf-8 -*-
"""角色选择与创建：像切换游戏存档一样切换整套求职数据。"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from core import profiles
from core.readers import read_document_text
from ui.icons import themed_icon
from ui.motion import fade_in


SOURCE_LABELS = {
    "blank": "空白角色",
    "resume": "由成品简历创建",
    "legacy": "沿用原有数据",
}


class RoleDialog(QDialog):
    def __init__(self, parent=None, startup: bool = False, protected_id: str = ""):
        super().__init__(parent)
        self.startup = bool(startup)
        self.protected_id = str(protected_id or "")
        self._current_id = ""
        self.selected_id = ""
        first_run = self.startup and not self.protected_id and not profiles.list_profiles()
        self.setWindowTitle("欢迎使用 · 创建角色" if first_run else "选择 / 管理角色")
        self.resize(680, 640)
        self._build()
        self._reload()
        fade_in(self, 200)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel(
            "先建立一个角色"
            if self.startup and not self.protected_id and not profiles.list_profiles()
            else "选择工作角色"
        )
        title.setObjectName("pageTitle")
        root.addWidget(title)
        intro = QLabel(
            "每个角色拥有独立的个人履历、求职意向、岗位池、评分与文字简历。"
            "接口 Key 和主题设置由所有角色共享。"
        )
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.current_label = QLabel("")
        self.current_label.setObjectName("success")
        root.addWidget(self.current_label)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        self.list.currentItemChanged.connect(lambda _current, _previous: self._update_actions())
        card_layout.addWidget(self.list, 1)
        root.addWidget(card, 1)

        self.empty_hint = QLabel(
            "还没有角色。可以新建空白角色，或从一份成品简历创建角色。"
            "如果检测到旧版数据，也可以原样沿用。"
        )
        self.empty_hint.setObjectName("hint")
        self.empty_hint.setWordWrap(True)
        root.addWidget(self.empty_hint)

        self.btn_adopt = QPushButton("沿用现有数据创建角色")
        self.btn_adopt.setObjectName("secondary")
        self.btn_adopt.setToolTip("复制旧履历、岗位池与评分到新角色，原数据不会被移动或删除")
        self.btn_adopt.clicked.connect(self._create_legacy)
        root.addWidget(self.btn_adopt)

        create_row = QHBoxLayout()
        self.btn_blank = QPushButton("新建空白角色")
        self.btn_blank.clicked.connect(self._create_blank)
        self.btn_resume = QPushButton("从成品简历创建…")
        self.btn_resume.clicked.connect(self._create_from_resume)
        create_row.addWidget(self.btn_blank)
        create_row.addWidget(self.btn_resume)
        create_row.addStretch(1)
        root.addLayout(create_row)

        action_row = QHBoxLayout()
        self.btn_delete = QPushButton("删除角色")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.setIcon(themed_icon("trash", 15))
        self.btn_delete.clicked.connect(self._delete_selected)
        action_row.addWidget(self.btn_delete)
        action_row.addSpacing(6)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        action_row.addWidget(cancel)
        action_row.addStretch(1)
        self.btn_switch = QPushButton("切换到此角色")
        self.btn_switch.setObjectName("primary")
        self.btn_switch.clicked.connect(self._accept_selected)
        action_row.addWidget(self.btn_switch)
        root.addLayout(action_row)

    def _reload(self):
        items = profiles.list_profiles()
        active = profiles.active_profile()
        self._current_id = (active or {}).get("id") or self.protected_id
        current = profiles.get_profile(self._current_id) if self._current_id else None
        self.list.clear()
        current_row = -1
        for index, profile in enumerate(items):
            source = SOURCE_LABELS.get(profile.get("source") or "", "角色")
            detail = source
            if profile.get("source_file"):
                detail += " · " + Path(profile["source_file"]).name
            label = "%s\n%s" % (profile.get("name") or "未命名角色", detail)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, profile["id"])
            item.setToolTip("%s\n创建：%s\n最近使用：%s" % (
                detail, profile.get("created_at") or "-", profile.get("updated_at") or "-"
            ))
            if self._current_id == profile["id"]:
                item.setText(label + "\n当前角色")
                current_row = index
                item.setToolTip(item.toolTip() + "\n当前角色不能直接删除")
            self.list.addItem(item)
        if current_row >= 0:
            self.list.setCurrentRow(current_row)
            self.current_label.setText("当前角色：%s" % ((current or {}).get("name") or "未命名角色"))
        elif items:
            self.list.setCurrentRow(0)
            self.current_label.setText("请选择要切换的角色")
        else:
            self.current_label.clear()
        has_items = bool(items)
        self.list.setVisible(has_items)
        self.empty_hint.setVisible(not has_items)
        self.btn_switch.setEnabled(has_items)
        self.btn_adopt.setVisible(profiles.legacy_available())
        self._update_actions()

    def _selected(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.UserRole)) if item else ""

    def _update_actions(self):
        profile_id = self._selected()
        can_delete = bool(profile_id) and profile_id != self._current_id
        self.btn_delete.setEnabled(can_delete)
        if not profile_id:
            self.btn_delete.setToolTip("请先选择一个角色")
        elif not can_delete:
            self.btn_delete.setToolTip("当前角色不能删除；请先切换到其他角色")
        else:
            self.btn_delete.setToolTip("永久删除这个角色及其全部本地数据")

    def _accept_selected(self):
        profile_id = self._selected()
        if not profile_id:
            QMessageBox.information(self, "请选择角色", "请先在列表里选择一个角色。")
            return
        self.selected_id = profile_id
        self.accept()

    def _delete_selected(self):
        profile_id = self._selected()
        if not profile_id:
            QMessageBox.information(self, "请选择角色", "请先在列表里选择一个角色。")
            return
        if profile_id == self._current_id:
            QMessageBox.information(
                self, "当前角色不能删除",
                "请先切换到其他角色，再删除这个角色。",
            )
            return
        record = profiles.get_profile(profile_id)
        if not record:
            QMessageBox.warning(self, "角色不存在", "这个角色可能已经被删除，请刷新列表。")
            self._reload()
            return
        name = record.get("name") or "未命名角色"
        typed, accepted = QInputDialog.getText(
            self,
            "删除角色",
            "将永久删除角色「%s」及其个人履历、意向、岗位池、评分和文字简历。\n"
            "此操作不会删除接口 Key 和主题设置。\n\n"
            "请输入角色名称以确认：" % name,
        )
        if not accepted:
            return
        if str(typed or "").strip() != name:
            QMessageBox.warning(self, "名称不一致", "角色名称不匹配，已取消删除。")
            return
        try:
            profiles.delete_profile(profile_id)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.selected_id = ""
        self._reload()
        QMessageBox.information(self, "角色已删除", "已删除角色「%s」及其本地数据。" % name)

    def _ask_name(self, default: str) -> str:
        name, accepted = QInputDialog.getText(self, "角色名称", "给这个角色起个名字：", text=default)
        return name.strip() if accepted else ""

    def _select_created(self, record: dict):
        self.selected_id = record["id"]
        self._reload()
        self.accept()

    def _create_blank(self):
        name = self._ask_name("我的角色")
        if not name:
            return
        try:
            record = profiles.create_profile(name)
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        self._select_created(record)

    def _create_legacy(self):
        name = self._ask_name("现有数据")
        if not name:
            return
        try:
            record = profiles.create_profile(name, adopt_legacy=True)
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        self._select_created(record)

    def _create_from_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择成品简历", "", "简历文件 (*.txt *.md *.docx *.pdf);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            text = read_document_text(path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", "无法读取该文件：\n%s" % exc)
            return
        text = str(text or "").strip()
        if not text:
            QMessageBox.warning(self, "没有内容", "没有提取到文字，可能是扫描版 PDF。")
            return
        default = Path(path).stem[:40] or "我的角色"
        name = self._ask_name(default)
        if not name:
            return
        try:
            record = profiles.create_profile(
                name, initial_text=text, source_file=path
            )
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        QMessageBox.information(
            self, "角色已创建",
            "已提取简历原文并建立角色。导入只做文字抽取，请稍后在「我的履历」核对事实。",
        )
        self._select_created(record)

