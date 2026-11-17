# -*- coding: utf-8 -*-
"""导出选项：先选格式与目标文件夹，再执行逐岗位导出。"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QStandardPaths
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from core.export_resumes import FORMAT_LABELS
from ui.motion import fade_in


class ExportDialog(QDialog):
    def __init__(self, parent=None, count: int = 1, title: str = "导出文字简历", preview: str = "公司_岗位_短ID.docx"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self._build(count, preview)
        fade_in(self, 160)

    def _build(self, count: int, preview: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        title = QLabel("选择导出格式与位置")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        note = QLabel(
            "每个岗位会单独生成一个文件，不会把多个岗位塞进同一个 Word。"
            "Excel 也按岗位拆分；文件名会自动附加短 ID 防止重名。"
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        root.addWidget(note)

        count_label = QLabel("本次将导出 %d 份文字简历" % max(0, int(count)))
        count_label.setObjectName("sectionTitle")
        root.addWidget(count_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("文件格式"))
        self.format = QComboBox()
        for key, label in FORMAT_LABELS.items():
            self.format.addItem(label, key)
        row.addWidget(self.format, 1)
        root.addLayout(row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("目标文件夹"))
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        default_folder = str(Path(documents or Path.home()) / "文字简历导出")
        self.folder = QLineEdit(default_folder)
        self.folder.setCursorPosition(0)
        self.folder.setToolTip(default_folder)
        folder_row.addWidget(self.folder, 1)
        browse = QPushButton("选择…")
        browse.clicked.connect(self._pick_folder)
        folder_row.addWidget(browse)
        root.addLayout(folder_row)

        self.preview = QLabel("命名示例：%s" % preview)
        self.preview.setObjectName("muted")
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)
        self.format.currentIndexChanged.connect(self._update_preview)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.ok = QPushButton("开始导出")
        self.ok.setObjectName("primary")
        self.ok.setEnabled(count > 0)
        self.ok.clicked.connect(self._accept)
        actions.addWidget(self.ok)
        root.addLayout(actions)

    def _update_preview(self):
        stem = "公司_岗位_短ID"
        ext = {"docx": ".docx", "md": ".md", "xlsx": ".xlsx"}.get(self.format.currentData(), ".docx")
        self.preview.setText("命名示例：%s%s" % (stem, ext))

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择导出文件夹", self.folder.text())
        if path:
            self.folder.setText(path)

    def _accept(self):
        if not self.folder.text().strip():
            self.folder.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return str(self.format.currentData()), self.folder.text().strip()
