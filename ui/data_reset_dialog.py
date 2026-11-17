# -*- coding: utf-8 -*-
"""Irreversible local-data reset confirmation."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from ui.icons import themed_icon


CONFIRM_WORD = "清空"


class ClearDataDialog(QDialog):
    """Require an explicit typed confirmation before deleting local data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("clearDataDialog")
        self.setWindowTitle("清空所有本地数据")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMaximumWidth(640)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(themed_icon("alert", 24).pixmap(24, 24))
        icon.setFixedSize(28, 28)
        header.addWidget(icon, 0, Qt.AlignTop)

        copy = QVBoxLayout()
        copy.setSpacing(3)
        title = QLabel("清空所有本地数据？")
        title.setObjectName("dangerDialogTitle")
        copy.addWidget(title)
        subtitle = QLabel("此操作会永久删除本机上的个人工作数据，无法撤销。")
        subtitle.setObjectName("dangerDialogSubtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(subtitle)
        header.addLayout(copy, 1)
        layout.addLayout(header)

        notice = QFrame()
        notice.setObjectName("dangerNotice")
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(13, 11, 13, 11)
        notice_layout.setSpacing(5)
        heading = QLabel("将删除")
        heading.setObjectName("dangerNoticeTitle")
        notice_layout.addWidget(heading)
        for text in (
            "全部角色、个人履历、求职意向与角色切换记录",
            "岗位池、意向评分、文字简历、备份与版本记录",
            "运行日志、窗口位置和上次打开页面的状态",
        ):
            item = QLabel("•  " + text)
            item.setObjectName("dangerNoticeBody")
            item.setWordWrap(True)
            notice_layout.addWidget(item)
        layout.addWidget(notice)

        self.include_config = QCheckBox("同时删除 API Key 与模型配置（config.json）")
        self.include_config.setToolTip(
            "默认保留接口配置。勾选后下一次启动需要重新填写接口地址、模型和 API Key。"
        )
        layout.addWidget(self.include_config)

        keep_note = QLabel(
            "默认保留 config.json。清空完成后应用会重新启动，并进入首次创建角色的流程。"
        )
        keep_note.setObjectName("fieldHelp")
        keep_note.setWordWrap(True)
        layout.addWidget(keep_note)

        confirm_label = QLabel("请输入“%s”两个字以确认：" % CONFIRM_WORD)
        confirm_label.setObjectName("fieldLabel")
        layout.addWidget(confirm_label)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setPlaceholderText(CONFIRM_WORD)
        self.confirm_edit.setClearButtonEnabled(True)
        self.confirm_edit.textChanged.connect(self._update_ready)
        self.confirm_edit.returnPressed.connect(self._accept_if_ready)
        layout.addWidget(self.confirm_edit)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)
        self.btn_clear = QPushButton("永久清空")
        self.btn_clear.setObjectName("dangerSolid")
        self.btn_clear.setIcon(themed_icon("trash", 15))
        self.btn_clear.setAutoDefault(False)
        self.btn_clear.setEnabled(False)
        self.btn_clear.clicked.connect(self.accept)
        buttons.addWidget(self.btn_clear)
        layout.addLayout(buttons)

    def _update_ready(self, text: str):
        self.btn_clear.setEnabled(str(text or "").strip() == CONFIRM_WORD)

    def _accept_if_ready(self):
        if self.btn_clear.isEnabled():
            self.accept()

    def delete_config_requested(self) -> bool:
        return self.include_config.isChecked()
