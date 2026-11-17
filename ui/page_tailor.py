# -*- coding: utf-8 -*-
"""页面 2：岗位定制（粘贴 JD -> 解析 -> 匹配矩阵 -> 生成自适应简历）。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from core import generate as core_generate
from core import jd as core_jd
from core import match as core_match
from core import models, store
from ui.dialogs import IssueReportDialog
from ui.worker import Worker, WorkerKeeper


class TailorPage(QWidget):
    resume_generated = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.keeper = WorkerKeeper()
        self.profile = store.load_profile()
        self.job = None
        self.matrix = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)

        jd_box = QGroupBox("目标岗位（把招聘网站上的 JD 整段粘贴进来）")
        jd_layout = QVBoxLayout(jd_box)
        self.jd_text = QPlainTextEdit()
        self.jd_text.setPlaceholderText(
            "例如：\n岗位职责：负责机器视觉方案的现场调试与交付…\n任职要求：熟悉 PLC、TCP/IP 通讯…"
        )
        self.jd_text.setFixedHeight(140)
        jd_layout.addWidget(self.jd_text)

        row = QHBoxLayout()
        self.btn_parse = QPushButton("解析岗位")
        self.btn_parse.clicked.connect(self._on_parse)
        row.addWidget(self.btn_parse)
        self.btn_match = QPushButton("匹配我的履历")
        self.btn_match.setEnabled(False)
        self.btn_match.clicked.connect(self._on_match)
        row.addWidget(self.btn_match)
        row.addStretch(1)
        jd_layout.addLayout(row)

        self.parse_result = QTextBrowser()
        self.parse_result.setFixedHeight(110)
        self.parse_result.setHtml('<p style="color:#888888;">解析结果会显示在这里。</p>')
        jd_layout.addWidget(self.parse_result)
        root.addWidget(jd_box)

        matrix_box = QGroupBox("匹配矩阵（哪些要求你有真实经历、哪些是真缺口）")
        matrix_layout = QVBoxLayout(matrix_box)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["重点", "岗位要求", "类型", "我方证据", "状态 / 说明"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 170)
        self.table.setMinimumHeight(180)
        matrix_layout.addWidget(self.table)
        self.gap_label = QLabel("")
        self.gap_label.setWordWrap(True)
        self.gap_label.setStyleSheet("color: #b26a00;")
        matrix_layout.addWidget(self.gap_label)
        root.addWidget(matrix_box, 1)

        entry_box = QGroupBox("参与本次生成的履历条目（默认全选，可取消不想突出的经历）")
        entry_layout = QVBoxLayout(entry_box)
        self.entry_list = QListWidget()
        self.entry_list.setMinimumHeight(130)
        entry_layout.addWidget(self.entry_list)
        row2 = QHBoxLayout()
        for text, state in (("全选", True), ("全不选", False)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, s=state: self._set_all_entries(s))
            row2.addWidget(btn)
        row2.addStretch(1)
        entry_layout.addLayout(row2)
        root.addWidget(entry_box)

        bottom = QHBoxLayout()
        self.btn_generate = QPushButton("生成自适应简历")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._on_generate)
        bottom.addWidget(self.btn_generate)
        bottom.addStretch(1)
        root.addLayout(bottom)

    # ------------------------------------------------------------ 工具
    def _set_busy(self, busy: bool):
        for btn in (self.btn_parse, self.btn_match, self.btn_generate):
            btn.setEnabled(not busy)
        if not busy:
            self.btn_match.setEnabled(self.job is not None)
            self.btn_generate.setEnabled(self.job is not None and bool(self.matrix))

    def _entry_label(self, entry_id: str) -> str:
        for spec in models.SECTION_SPECS:
            entry = models.find_entry(self.profile, spec["key"], entry_id)
            if entry is not None:
                return "[%s] %s" % (spec["title"], models.entry_display(spec["key"], entry))
        return entry_id

    # ------------------------------------------------------------ 解析 JD
    def _on_parse(self):
        text = self.jd_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先粘贴岗位 JD。")
            return
        llm = self.ctx.llm()
        self._set_busy(True)
        worker = Worker(lambda cb: core_jd.parse_jd(text, llm, progress=cb))
        worker.progress.connect(self.progress)
        worker.done.connect(self._on_parsed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._set_busy(False))
        self.keeper.start(worker)

    def _on_parsed(self, job: dict):
        self.job = job
        lines = core_jd.summary_lines(job)
        if lines:
            html = "<br>".join("<b>%s</b>%s" % (line.split("：")[0] + "：", "：".join(line.split("：")[1:])) for line in lines)
        else:
            html = "未解析出结构化信息，请检查 JD 内容。"
        self.parse_result.setHtml(html)
        self.btn_match.setEnabled(True)
        self.status.emit("岗位解析完成")

    # ------------------------------------------------------------ 匹配
    def _on_match(self):
        if not self.job:
            return
        self.profile = store.load_profile()
        if not any(models.iter_entries(self.profile, spec["key"]) for spec in models.SECTION_SPECS):
            QMessageBox.warning(self, "提示", "主履历还是空的，请先去「我的履历」填写。")
            return
        llm = self.ctx.llm()
        job = self.job
        profile = self.profile
        self._set_busy(True)
        worker = Worker(lambda cb: core_match.build_matrix(job, profile, llm, progress=cb))
        worker.progress.connect(self.progress)
        worker.done.connect(self._on_matched)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._set_busy(False))
        self.keeper.start(worker)

    def _on_matched(self, rows: list):
        self.matrix = rows
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, check)
            values = [
                row.get("requirement", ""),
                row.get("type", ""),
                "、".join(self._entry_label(e) for e in row.get("evidence_ids") or []) or "无",
                "%s  %s" % (row.get("status", ""), row.get("note", "")),
            ]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                if row.get("status") == "真实缺口":
                    item.setForeground(Qt.darkYellow)
                self.table.setItem(r, col, item)
        gaps = core_match.real_gaps(rows)
        if gaps:
            self.gap_label.setText(
                "真实缺口 %d 条 —— 这些要求主履历里没有依据，简历不会替你编造：%s"
                % (len(gaps), "；".join(g["requirement"] for g in gaps[:5]))
            )
        else:
            self.gap_label.setText("未发现明显缺口。")
        self._fill_entry_list()
        self.btn_generate.setEnabled(True)
        self.status.emit("匹配完成，共 %d 条要求" % len(rows))

    def _fill_entry_list(self):
        self.profile = store.load_profile()
        referenced = set()
        for row in self.matrix:
            referenced.update(row.get("evidence_ids") or [])
        self.entry_list.clear()
        for spec in models.SECTION_SPECS:
            for entry in models.iter_entries(self.profile, spec["key"]):
                label = "[%s] %s" % (spec["title"], models.entry_display(spec["key"], entry))
                if entry.get("id") in referenced:
                    label += "   ★ 与岗位相关"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, entry.get("id"))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.entry_list.addItem(item)

    def _set_all_entries(self, state: bool):
        for i in range(self.entry_list.count()):
            self.entry_list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)

    # ------------------------------------------------------------ 生成
    def _on_generate(self):
        if not self.job or not self.matrix:
            return
        for r, row in enumerate(self.matrix):
            item = self.table.item(r, 0)
            row["selected"] = bool(item and item.checkState() == Qt.Checked)
        checked = []
        for i in range(self.entry_list.count()):
            item = self.entry_list.item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.data(Qt.UserRole))
        if not checked:
            QMessageBox.warning(self, "提示", "至少要勾选一条履历条目。")
            return

        self.profile = store.load_profile()
        profile = self.profile
        job = self.job
        matrix = self.matrix
        allowed = core_match.selected_entry_ids(matrix, checked)
        llm = self.ctx.llm()
        language = self.ctx.language()
        self._set_busy(True)
        worker = Worker(
            lambda cb: core_generate.generate_tailored_resume(
                profile, job, allowed, llm, language, matrix=matrix, progress=cb
            )
        )
        worker.progress.connect(self.progress)
        worker.done.connect(self._on_generated)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._set_busy(False))
        self.keeper.start(worker)

    def _on_generated(self, result):
        title = "%s · %s" % (self.job.get("company") or "目标岗位", self.job.get("role") or "未命名岗位")
        doc = core_generate.finalize_doc(
            result["doc"], self.profile, "tailored", title.strip(" ·"), self.ctx.model_name(),
            job=self.job, matrix=self.matrix,
        )
        doc["issues"] = result["issues"]
        vid = store.save_version(doc)
        note = "已保存为版本「%s」（生成 %d 次）。" % (vid, result["attempts"])
        IssueReportDialog("自适应简历生成结果", result["issues"], self, note).exec_()
        self.resume_generated.emit(vid)
        self.status.emit("自适应简历已生成：%s" % vid)

    def _on_failed(self, message):
        QMessageBox.critical(self, "操作失败", message)
