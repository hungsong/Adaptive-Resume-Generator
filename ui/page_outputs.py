# -*- coding: utf-8 -*-
"""页面 3：文字版定向简历、筛选与逐岗位导出。"""
from __future__ import annotations

import datetime as _dt

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QShortcut, QSplitter, QVBoxLayout, QWidget,
)

from core import export_resumes, guard, intent, jobs as job_store, profile_text, tailor_text
from ui import browser
from ui.components import Card, ChipLabel, Divider, PageHeader, secondary_button
from ui.icons import themed_icon
from ui.export_dialog import ExportDialog


class OutputsPage(QWidget):
    status = pyqtSignal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.jobs = []
        self.doc = None
        self._current_row = -1
        self._dirty = False
        self._loading_editor = False
        self._refreshing = False
        self._build()
        self.refresh()

    def _build_legacy(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("文字简历")
        title.setObjectName("pageTitle")
        title_box.addWidget(title)
        subtitle = QLabel("只提供内容；样式由你自选。每个岗位可独立导出")
        subtitle.setObjectName("hint")
        title_box.addWidget(subtitle)
        bar.addLayout(title_box)
        bar.addStretch(1)
        self.btn_copy_all = QPushButton("复制全文")
        self.btn_copy_all.setObjectName("secondary")
        self.btn_copy_all.clicked.connect(self._copy_all)
        bar.addWidget(self.btn_copy_all)
        self.btn_export = QPushButton("导出当前…")
        self.btn_export.setObjectName("secondary")
        self.btn_export.clicked.connect(self._export_current)
        bar.addWidget(self.btn_export)
        self.btn_export_all = QPushButton("导出全部文字简历…")
        self.btn_export_all.setObjectName("primary")
        self.btn_export_all.setToolTip("按当前筛选结果逐岗位导出，每个岗位一个文件  Ctrl+Shift+E")
        self.btn_export_all.clicked.connect(self._export_all)
        bar.addWidget(self.btn_export_all)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(7)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索公司、岗位、城市…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)
        left_layout.addWidget(self.search)
        filter_row = QHBoxLayout()
        self.filter = QComboBox()
        for label, value in (
            ("全部简历", "all"), ("人工修改", "manual"), ("有校验提醒", "review"),
        ):
            self.filter.addItem(label, value)
        self.filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.filter, 1)
        self.sort = QComboBox()
        for label, value in (
            ("最新生成", "recent"), ("意向分最高", "score"),
            ("公司名称", "company"), ("薪资最高", "salary"),
        ):
            self.sort.addItem(label, value)
        self.sort.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.sort, 1)
        left_layout.addLayout(filter_row)
        self.count_label = QLabel("0 份")
        self.count_label.setObjectName("muted")
        left_layout.addWidget(self.count_label)
        self.list = QListWidget()
        self.list.setMinimumWidth(300)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list, 1)
        splitter.addWidget(left)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)
        self.meta = QLabel("尚未生成文字简历")
        self.meta.setObjectName("sectionTitle")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        self.link_button = QPushButton("打开原岗位 ↗")
        self.link_button.setObjectName("linkButton")
        self.link_button.clicked.connect(self._open_current_link)
        layout.addWidget(self.link_button, 0, Qt.AlignLeft)
        self.link_hint = QLabel("若链接打不开，可能岗位已取消；本工具不校验岗位时效性。")
        self.link_hint.setObjectName("hint")
        self.link_hint.setWordWrap(True)
        layout.addWidget(self.link_hint)

        row = QHBoxLayout()
        self.save_state = QLabel("")
        self.save_state.setObjectName("muted")
        row.addWidget(self.save_state)
        row.addStretch(1)
        self.btn_save = QPushButton("保存修改")
        self.btn_save.setObjectName("secondary")
        self.btn_save.clicked.connect(self._save_edit)
        row.addWidget(self.btn_save)
        layout.addLayout(row)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在「岗位池」勾选岗位并生成后，这里会显示文字简历。")
        self.editor.textChanged.connect(self._mark_dirty)
        layout.addWidget(self.editor, 1)
        tip = QLabel(
            "不输出 PDF、Word 模板或版式。复制文字后，粘贴到你喜欢的简历样式即可。\n"
            "人工修改会按整篇保存；导出时会使用最新正文，不会沿用旧分块。"
        )
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        splitter.addWidget(right)
        splitter.setSizes([330, 900])
        root.addWidget(splitter, 1)
        self._set_enabled(False)

        self.shortcut_export_all = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.shortcut_export_all.activated.connect(self._export_all)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self._focus_search)
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self._save_edit)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        header = PageHeader(
            "简历库",
            "按岗位保存和编辑纯文字内容，套用样式由你决定。",
            "RESUME LIBRARY / OUTPUTS",
        )
        self.btn_copy_all = secondary_button("复制全文", "copy")
        self.btn_copy_all.clicked.connect(self._copy_all)
        header.add_action(self.btn_copy_all)
        self.btn_export = secondary_button("导出当前", "download")
        self.btn_export.clicked.connect(self._export_current)
        header.add_action(self.btn_export)
        self.btn_export_all = QPushButton("导出全部")
        self.btn_export_all.setObjectName("primary")
        self.btn_export_all.setIcon(themed_icon("download", 15))
        self.btn_export_all.setToolTip("按当前筛选结果逐岗位导出，每个岗位一个文件  Ctrl+Shift+E")
        self.btn_export_all.clicked.connect(self._export_all)
        header.add_action(self.btn_export_all)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_document_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])
        root.addWidget(splitter, 1)

        self.shortcut_export_all = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.shortcut_export_all.activated.connect(self._export_all)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self._focus_search)
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self._save_edit)

    def _build_list_panel(self) -> Card:
        card = Card()
        card.setObjectName("tableCard")
        card.setMinimumWidth(280)
        card.setMaximumWidth(380)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("tableToolbar")
        head = QHBoxLayout(toolbar)
        head.setContentsMargins(12, 10, 10, 9)
        copy = QVBoxLayout()
        copy.setSpacing(0)
        title = QLabel("已保存简历")
        title.setObjectName("tableTitle")
        copy.addWidget(title)
        self.count_label = QLabel("0 份")
        self.count_label.setObjectName("tableMeta")
        copy.addWidget(self.count_label)
        head.addLayout(copy, 1)
        self.btn_reset_filters = QPushButton()
        self.btn_reset_filters.setObjectName("iconButton")
        self.btn_reset_filters.setIcon(themed_icon("filter", 15))
        self.btn_reset_filters.setToolTip("重置搜索、筛选与排序")
        self.btn_reset_filters.clicked.connect(self._reset_filters)
        head.addWidget(self.btn_reset_filters)
        layout.addWidget(toolbar)

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(9, 8, 9, 8)
        body.setSpacing(7)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索公司、岗位、城市…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)
        body.addWidget(self.search)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(5)
        self.filter = QComboBox()
        for label, value in (
            ("全部简历", "all"), ("人工修改", "manual"), ("有校验提醒", "review"),
        ):
            self.filter.addItem(label, value)
        self.filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.filter, 1)
        self.sort = QComboBox()
        for label, value in (
            ("最新生成", "recent"), ("意向分最高", "score"),
            ("公司名称", "company"), ("薪资最高", "salary"),
        ):
            self.sort.addItem(label, value)
        self.sort.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.sort, 1)
        body.addLayout(filter_row)
        body.addWidget(Divider())
        self.list = QListWidget()
        self.list.setObjectName("outputList")
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._on_select)
        body.addWidget(self.list, 1)
        layout.addWidget(content, 1)
        return card

    def _build_document_panel(self) -> Card:
        card = Card()
        card.setObjectName("documentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("editorToolbar")
        head = QHBoxLayout(toolbar)
        head.setContentsMargins(18, 12, 14, 11)
        head.setSpacing(8)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.document_title = QLabel("尚未生成文字简历")
        self.document_title.setObjectName("documentTitle")
        self.document_title.setWordWrap(True)
        copy.addWidget(self.document_title)
        self.meta = QLabel("从岗位工作台生成后，这里会显示可编辑的纯文字版本。")
        self.meta.setObjectName("documentMeta")
        self.meta.setWordWrap(True)
        copy.addWidget(self.meta)
        head.addLayout(copy, 1)
        self.link_button = QPushButton("打开原岗位")
        self.link_button.setObjectName("linkButton")
        self.link_button.setIcon(themed_icon("external", 14))
        self.link_button.clicked.connect(self._open_current_link)
        head.addWidget(self.link_button, 0, Qt.AlignTop)
        layout.addWidget(toolbar)
        layout.addWidget(Divider())

        self.validation_banner = QFrame()
        self.validation_banner.setObjectName("validationBanner")
        banner = QHBoxLayout(self.validation_banner)
        banner.setContentsMargins(18, 6, 14, 6)
        banner.setSpacing(7)
        self.validation_icon = QLabel("✓")
        self.validation_icon.setObjectName("success")
        banner.addWidget(self.validation_icon)
        self.validation_text = QLabel("本地校验会在保存后更新。")
        self.validation_text.setObjectName("validationText")
        self.validation_text.setWordWrap(True)
        banner.addWidget(self.validation_text, 1)
        self.validation_chip = ChipLabel("等待简历", "neutral")
        banner.addWidget(self.validation_chip)
        layout.addWidget(self.validation_banner)

        self.link_hint = QLabel("若链接打不开，可能岗位已取消；本工具不校验岗位时效性。")
        self.link_hint.setObjectName("fieldHelp")
        self.link_hint.setWordWrap(True)
        self.link_hint.setContentsMargins(18, 5, 18, 0)
        layout.addWidget(self.link_hint)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("documentEditor")
        self.editor.setPlaceholderText("在「岗位工作台」勾选岗位并生成后，这里会显示文字简历。")
        self.editor.textChanged.connect(self._mark_dirty)
        layout.addWidget(self.editor, 1)

        footer = QFrame()
        footer.setObjectName("documentFooter")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(16, 7, 12, 7)
        bottom.setSpacing(8)
        self.save_state = QLabel("")
        self.save_state.setObjectName("muted")
        bottom.addWidget(self.save_state)
        bottom.addStretch(1)
        plain = QLabel("纯文本内容 · 无版式模板")
        plain.setObjectName("muted")
        bottom.addWidget(plain)
        self.btn_save = QPushButton("保存修改")
        self.btn_save.setObjectName("secondary")
        self.btn_save.setIcon(themed_icon("save", 14))
        self.btn_save.clicked.connect(self._save_edit)
        bottom.addWidget(self.btn_save)
        layout.addWidget(footer)
        self._set_enabled(False)
        return card

    def _reset_filters(self):
        self.search.clear()
        self.filter.setCurrentIndex(0)
        self.sort.setCurrentIndex(0)

    # ------------------------------------------------------------ 列表与筛选
    def refresh(self):
        if self._dirty and self.doc:
            if not self._commit_edit(interactive=False):
                return
        current = self.doc.get("id") if isinstance(self.doc, dict) else None
        self._refreshing = True
        self.jobs = [j for j in job_store.load_pool() if (j.get("tailored") or {}).get("text")]
        self._apply_filters(preserve_id=current)
        self._refreshing = False

    def _filtered_jobs(self) -> list:
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        mode = self.filter.currentData() if hasattr(self, "filter") else "all"
        jobs = []
        for job in self.jobs:
            tailored = job.get("tailored") or {}
            if mode == "manual" and not tailored.get("manually_edited"):
                continue
            if mode == "review" and not tailored.get("issues"):
                continue
            if query:
                blob = "\n".join([
                    str(job.get("company") or ""), str(job.get("title") or ""),
                    str(job.get("city") or ""), str(job.get("salary") or ""),
                ]).lower()
                if query not in blob:
                    continue
            jobs.append(job)
        key = self.sort.currentData() if hasattr(self, "sort") else "recent"
        if key == "score":
            jobs.sort(key=lambda j: int((j.get("intent") or {}).get("score") or -1), reverse=True)
        elif key == "company":
            jobs.sort(key=lambda j: ((j.get("company") or "").lower(), (j.get("title") or "").lower()))
        elif key == "salary":
            def salary_high(job):
                parsed = intent.parse_salary_range(job.get("salary") or "")
                return parsed[1] if parsed else -1
            jobs.sort(key=salary_high, reverse=True)
        else:
            jobs.sort(
                key=lambda j: (
                    (j.get("tailored") or {}).get("generated_at") or "",
                    (j.get("tailored") or {}).get("edited_at") or "",
                    j.get("updated_at") or "",
                ),
                reverse=True,
            )
        return jobs

    def _apply_filters(self, preserve_id=None):
        if not hasattr(self, "list"):
            return
        if self._dirty and self.doc and not self._refreshing:
            if not self._commit_edit(interactive=False):
                return
        current = preserve_id or (self.doc.get("id") if isinstance(self.doc, dict) else None)
        jobs = self._filtered_jobs()
        self.list.blockSignals(True)
        self.list.clear()
        for job in jobs:
            tailored = job.get("tailored") or {}
            score = (job.get("intent") or {}).get("score", "-")
            flags = []
            if tailored.get("manually_edited"):
                flags.append("人工改")
            if tailored.get("issues"):
                flags.append("有提醒")
            flag_text = "｜" + " · ".join(flags) if flags else ""
            label = "%s 分%s\n%s" % (score, flag_text, job_store.display_name(job))
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, job.get("id"))
            item.setToolTip("%s\n薪资：%s\n生成：%s" % (
                job_store.display_name(job), job.get("salary") or "-",
                tailored.get("generated_at") or tailored.get("edited_at") or "-",
            ))
            self.list.addItem(item)
        self.count_label.setText("当前筛选 %d 份 · 共 %d 份" % (len(jobs), len(self.jobs)))
        self.list.blockSignals(False)
        if not jobs:
            self.doc = None
            self._current_row = -1
            self._dirty = False
            self.document_title.setText("还没有符合条件的文字简历")
            self.meta.setText("去岗位工作台勾选岗位并生成，或调整左侧筛选。")
            self.link_button.setVisible(False)
            self.link_hint.setText("若链接打不开，可能岗位已取消；本工具不校验岗位时效性。")
            self._set_validation(None, [])
            self.save_state.clear()
            self._loading_editor = True
            self.editor.clear()
            self._loading_editor = False
            self._set_enabled(False)
            return
        target = next((i for i, j in enumerate(jobs) if j.get("id") == current), 0)
        self.list.setCurrentRow(target)
        # setCurrentRow 被 blockSignals 抑制时，必须显式载入正文，
        # 否则刷新、搜索和排序后右侧编辑器会停留在旧内容。
        self._load_row(target)

    def select_job(self, job_id: str) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == job_id:
                self.list.setCurrentRow(row)
                return True
        return False

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _set_enabled(self, enabled: bool):
        for widget in (self.btn_copy_all, self.btn_save, self.btn_export, self.editor):
            widget.setEnabled(enabled)
        self.btn_export_all.setEnabled(bool(self.jobs))

    def _mark_dirty(self):
        if self._loading_editor or self._refreshing or not self.doc:
            return
        self._dirty = True
        self.save_state.setText("有未保存修改")
        self.status.emit("文字简历有未保存修改")

    def _ask_unsaved(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("有未保存修改")
        box.setText("当前文字简历已修改，切换前怎么处理？")
        save_btn = box.addButton("保存修改", QMessageBox.AcceptRole)
        discard_btn = box.addButton("放弃修改", QMessageBox.DestructiveRole)
        box.addButton("取消切换", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is save_btn:
            return "save"
        if clicked is discard_btn:
            return "discard"
        return "cancel"

    def _on_select(self, row: int):
        if self._refreshing:
            return
        if self._dirty and self.doc and row != self._current_row:
            action = self._ask_unsaved()
            if action == "cancel":
                self.list.blockSignals(True)
                self.list.setCurrentRow(self._current_row)
                self.list.blockSignals(False)
                return
            if action == "save" and not self._commit_edit(interactive=False):
                return
            if action == "discard":
                self._dirty = False
        self._load_row(row)

    def _load_row(self, row: int):
        jobs = self._filtered_jobs()
        if not (0 <= row < len(jobs)):
            self.doc = None
            self._current_row = -1
            self._dirty = False
            self._set_enabled(False)
            return
        self.doc = jobs[row]
        self._current_row = row
        self._dirty = False
        self.save_state.clear()
        tailored = self.doc.get("tailored") or {}
        status = tailored.get("status") or "ok"
        score = (self.doc.get("intent") or {}).get("score", "-")
        self.document_title.setText(self.doc.get("title") or job_store.display_name(self.doc))
        self.meta.setText(
            "%s · %s · 意向 %s 分 · %s" % (
                self.doc.get("company") or "公司未识别",
                self.doc.get("city") or "城市未识别",
                score,
                tailored.get("generated_at") or tailored.get("edited_at") or "-",
            )
        )
        self._set_validation(status, tailored.get("issues") or [])
        url = str(self.doc.get("url") or "").strip()
        if url:
            self._current_url = url
            self.link_button.setToolTip(url)
            self.link_button.setVisible(True)
            self.link_hint.setText("若链接打不开，可能岗位已取消；本工具不校验岗位时效性。")
        else:
            self._current_url = ""
            self.link_button.setToolTip("原岗位链接缺失")
            self.link_button.setVisible(False)
            self.link_hint.setText("这条记录没有原岗位链接；不影响查看和导出当前文字简历。")
        self._loading_editor = True
        self.editor.setPlainText(tailored.get("text") or tailored.get("plain_text") or "")
        self._loading_editor = False
        self._set_enabled(True)

    def _open_current_link(self):
        if getattr(self, "_current_url", ""):
            ok, detail = browser.open_external_url(self._current_url)
            if not ok:
                self.link_hint.setText("链接打开失败，可能岗位已取消或页面不可访问。")
                self.status.emit("原岗位链接打开失败：%s" % detail)

    def _set_validation(self, status, issues: list):
        issues = issues or []
        if status is None:
            self.validation_banner.setObjectName("validationBanner")
            self.validation_icon.setText("✓")
            self.validation_icon.setObjectName("success")
            self.validation_text.setText("生成完成后，这里会显示本地事实校验结果。")
            self.validation_chip.setText("等待简历")
            self.validation_chip.set_variant("neutral")
        elif issues or status != "ok":
            self.validation_banner.setObjectName("validationWarning")
            self.validation_icon.setText("!")
            self.validation_icon.setObjectName("warning")
            self.validation_text.setText(
                "本地校验发现 %d 条需注意内容；请核对新增措辞能否在原始履历中追溯。" % len(issues)
            )
            self.validation_chip.setText("需核对")
            self.validation_chip.set_variant("warning")
        else:
            self.validation_banner.setObjectName("validationBanner")
            self.validation_icon.setText("✓")
            self.validation_icon.setObjectName("success")
            self.validation_text.setText("本地事实校验通过 · 内容可在原始履历中追溯。")
            self.validation_chip.setText("已通过")
            self.validation_chip.set_variant("success")
        for widget in (self.validation_banner, self.validation_icon):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # ------------------------------------------------------------ 编辑与导出
    def _copy_all(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.emit("已复制全文，共 %d 字" % len(text))

    def _save_edit(self):
        self._commit_edit(interactive=True)

    @property
    def has_unsaved(self) -> bool:
        return bool(self._dirty)

    def save_pending(self) -> bool:
        if not self._dirty or not self.doc:
            return True
        return self._commit_edit(interactive=False)

    def discard_pending(self):
        """Drop the in-memory edit state before an explicit data reset."""
        self._dirty = False

    def _commit_edit(self, interactive: bool = True) -> bool:
        if not self.doc:
            return False
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "内容为空", "文字简历不能为空。")
            return False
        profile = profile_text.load_profile_text().get("text", "")
        issues = guard.check_free_text_item(
            text, profile, [profile] if profile.strip() else [], "人工修改", max_chars=100000,
        )
        tailored = self.doc.setdefault("tailored", {})
        criteria = intent.load_criteria()
        tailored["text"] = text
        tailored["plain_text"] = text
        tailored["markdown"] = ""
        tailored["sections"] = []
        tailored["manually_edited"] = True
        tailored["edited_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tailored["issues"] = issues
        tailored["status"] = "needs_review" if guard.blocking(issues) else "ok"
        tailored["jd_hash"] = self.doc.get("jd_hash") or ""
        tailored["profile_hash"] = tailor_text.profile_hash(profile)
        tailored["criteria_hash"] = intent.criteria_signature(criteria)
        tailored["strength"] = criteria.get("rewrite_strength") or "standard"
        pool = job_store.load_pool()
        for job in pool:
            if job.get("id") == self.doc.get("id"):
                job["tailored"] = self.doc["tailored"]
                break
        job_store.save_pool(pool)
        self._dirty = False
        self.save_state.setText("已保存")
        self.status.emit("人工修改已保存：%s" % job_store.display_name(self.doc))
        if not interactive:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("修改已保存")
        box.setText("文字简历已保存。")
        if issues:
            box.setInformativeText("本地校验发现 %d 条需注意的内容，详见详细信息。" % len(issues))
            box.setDetailedText(guard.format_report(issues))
            box.setIcon(QMessageBox.Warning if guard.blocking(issues) else QMessageBox.Information)
        box.exec_()
        self.refresh()
        return True

    def _export_current(self):
        if not self.doc or not self.save_pending():
            return
        preview = export_resumes.base_filename(self.doc) + ".docx"
        dialog = ExportDialog(self, count=1, title="导出当前文字简历", preview=preview)
        if dialog.exec_() != dialog.Accepted:
            return
        fmt, folder = dialog.values()
        self._run_export([self.doc], fmt, folder)

    def _export_all(self):
        if not self.save_pending():
            return
        jobs = self._filtered_jobs()
        if not jobs:
            QMessageBox.information(self, "没有可导出的简历", "当前筛选结果为空。")
            return
        sample = export_resumes.base_filename(jobs[0]) + ".docx"
        dialog = ExportDialog(
            self, count=len(jobs), title="导出全部文字简历", preview=sample,
        )
        if dialog.exec_() != dialog.Accepted:
            return
        fmt, folder = dialog.values()
        self._run_export(jobs, fmt, folder)

    def _run_export(self, jobs: list, fmt: str, folder: str):
        self.status.emit("正在导出 %d 份文字简历…" % len(jobs))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = export_resumes.export_jobs(jobs, folder, fmt)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QApplication.restoreOverrideCursor()
        exported = report.get("exported") or []
        failures = report.get("failures") or []
        box = QMessageBox(self)
        box.setWindowTitle("导出完成" if not failures else "导出完成，但有失败")
        box.setText("已导出 %d 份，失败 %d 份\n\n位置：%s" % (
            len(exported), len(failures), report.get("folder") or folder,
        ))
        if failures:
            box.setDetailedText("\n".join(
                "%s：%s" % (f.get("job") or "-", f.get("error")) for f in failures
            ))
            box.setIcon(QMessageBox.Warning)
        else:
            box.setIcon(QMessageBox.Information)
        box.exec_()
        self.status.emit("文字简历导出完成：%d 份" % len(exported))

    def reload_for_profile(self):
        self._dirty = False
        self.doc = None
        self._current_row = -1
        self.search.clear()
        self.refresh()
