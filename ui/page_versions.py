# -*- coding: utf-8 -*-
"""页面 3：我的简历（版本列表 + 预览 + 编辑 + 导出）。"""
from __future__ import annotations

import datetime
import os
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
    QWidget,
)

from core import guard, render, store
from core.config import VERSIONS_DIR
from ui.dialogs import IssueReportDialog, ResumeEditorDialog


class VersionsPage(QWidget):
    status = pyqtSignal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.doc = None
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        title = QLabel("我的简历（基础版与各岗位版本，主履历不受影响）")
        title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        bar.addWidget(title)
        bar.addStretch(1)
        btn_refresh = QPushButton("刷新列表")
        btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(btn_refresh)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)

        left = QGroupBox("版本列表")
        left_layout = QVBoxLayout(left)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list)
        row = QHBoxLayout()
        btn_rename = QPushButton("重命名")
        btn_rename.clicked.connect(self._on_rename)
        btn_delete = QPushButton("删除")
        btn_delete.clicked.connect(self._on_delete)
        row.addWidget(btn_rename)
        row.addWidget(btn_delete)
        row.addStretch(1)
        left_layout.addLayout(row)
        splitter.addWidget(left)

        right = QGroupBox("预览")
        right_layout = QVBoxLayout(right)
        self.preview = QTextBrowser()
        right_layout.addWidget(self.preview, 1)
        row2 = QHBoxLayout()
        self.btn_edit = QPushButton("编辑内容")
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_pdf = QPushButton("导出 PDF")
        self.btn_pdf.setObjectName("primary")
        self.btn_pdf.clicked.connect(self._on_export_pdf)
        self.btn_md = QPushButton("导出 Markdown")
        self.btn_md.clicked.connect(self._on_export_markdown)
        self.btn_dir = QPushButton("打开版本目录")
        self.btn_dir.clicked.connect(self._open_dir)
        for btn in (self.btn_edit, self.btn_pdf, self.btn_md, self.btn_dir):
            row2.addWidget(btn)
        row2.addStretch(1)
        right_layout.addLayout(row2)
        self.flag_label = QLabel("")
        self.flag_label.setWordWrap(True)
        self.flag_label.setStyleSheet("color: #b26a00;")
        right_layout.addWidget(self.flag_label)
        splitter.addWidget(right)
        splitter.setSizes([320, 700])
        root.addWidget(splitter, 1)

        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        for btn in (self.btn_edit, self.btn_pdf, self.btn_md):
            btn.setEnabled(on)

    # ------------------------------------------------------------ 列表
    def refresh(self):
        self.list.clear()
        for meta in store.list_versions():
            kind = "基础" if meta["kind"] == "basic" else "岗位"
            item = QListWidgetItem("［%s］%s\n%s" % (kind, meta["title"], meta["created_at"]))
            item.setData(Qt.UserRole, meta["id"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.doc = None
            self.preview.setHtml(
                '<p style="color:#888888;">还没有生成过简历。先去「我的履历」生成基础简历，'
                "或在「岗位定制」里出定向版本。</p>"
            )
            self._set_enabled(False)

    def select_version(self, vid: str) -> bool:
        self.refresh()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == vid:
                self.list.setCurrentRow(i)
                return True
        return False

    def _on_select(self, row: int):
        if row < 0:
            return
        item = self.list.item(row)
        if item is None:
            return
        vid = item.data(Qt.UserRole)
        doc = store.load_version(vid)
        if doc is None:
            QMessageBox.warning(self, "读取失败", "版本文件不存在或已损坏：%s" % vid)
            return
        self.doc = doc
        self.preview.setHtml(render.build_html(doc))
        issues = doc.get("issues") or []
        flagged = sum(
            1
            for sec in doc.get("sections") or []
            for item in sec.get("items") or []
            if item.get("flagged") or any((b or {}).get("flagged") for b in (item.get("bullets") or []))
        )
        if issues:
            self.flag_label.setText(
                "该版本有 %d 条校验记录，其中 %d 处已标红（被拦截或待核实，请核对后再导出）。"
                % (len(issues), flagged)
            )
        else:
            self.flag_label.setText("")

    # ------------------------------------------------------------ 操作
    def _on_rename(self):
        if not self.doc:
            return
        text, ok = QInputDialog.getText(self, "重命名", "新名称：", text=self.doc.get("title", ""))
        if not ok or not text.strip():
            return
        self.doc["title"] = text.strip()
        vid = store.save_version(self.doc)
        self.select_version(vid)

    def _on_delete(self):
        if not self.doc:
            return
        if QMessageBox.question(self, "确认删除", "确定删除这个版本吗？（主履历不受影响）") != QMessageBox.Yes:
            return
        store.delete_version(self.doc["id"])
        self.doc = None
        self.refresh()
        self.status.emit("版本已删除")

    def _on_edit(self):
        if not self.doc:
            return
        dlg = ResumeEditorDialog(self.doc, self)
        if dlg.exec_() != dlg.Accepted:
            return
        doc = dlg.result_doc()
        profile = store.load_profile()
        issues = guard.check_resume(doc, profile)
        guard.flag_document(doc, issues)
        doc["issues"] = issues
        doc["edited_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        vid = store.save_version(doc)
        self.select_version(vid)
        IssueReportDialog("编辑后的校验结果", issues, self).exec_()
        self.status.emit("版本已保存：%s" % vid)

    def _default_name(self, suffix: str) -> str:
        doc = self.doc or {}
        name = (doc.get("header") or {}).get("name") or "简历"
        title = re.sub(r"[\\/:*?\"<>|]", "_", doc.get("title") or "简历")
        return "%s-%s.%s" % (name, title, suffix)

    def _on_export_pdf(self):
        if not self.doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", self._default_name("pdf"), "PDF 文件 (*.pdf)")
        if not path:
            return
        try:
            render.export_pdf(render.build_html(self.doc, show_flags=False), path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self._after_export(path, "PDF")

    def _on_export_markdown(self):
        if not self.doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 Markdown", self._default_name("md"), "Markdown 文件 (*.md)")
        if not path:
            return
        try:
            render.export_markdown(self.doc, path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self._after_export(path, "Markdown")

    def _after_export(self, path: str, kind: str):
        self.status.emit("%s 已导出：%s" % (kind, path))
        box = QMessageBox(self)
        box.setWindowTitle("导出完成")
        box.setText("%s 已导出：\n%s" % (kind, path))
        open_btn = box.addButton("打开文件", QMessageBox.AcceptRole)
        box.addButton("知道了", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is open_btn:
            try:
                os.startfile(path)
            except Exception as exc:
                QMessageBox.warning(self, "打开失败", str(exc))

    def _open_dir(self):
        try:
            os.startfile(str(VERSIONS_DIR))
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
