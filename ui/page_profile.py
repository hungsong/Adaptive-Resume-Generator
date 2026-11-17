# -*- coding: utf-8 -*-
"""页面 1：我的个人履历（一整段自由文本，原文即事实源）。"""
from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from core import profile_text
from core.readers import read_document_text
from ui.components import Card, ChipLabel, Divider, PageHeader, secondary_button
from ui.icons import themed_icon


class ProfilePage(QWidget):
    status = pyqtSignal(str)
    profile_saved = pyqtSignal()
    role_requested = pyqtSignal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._loading = True
        self._last_saved = ""
        self._source_file = ""
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1200)
        self._save_timer.timeout.connect(lambda: self._save(silent=True))
        self._build()
        self._load()
        self._loading = False

    def _build_legacy(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)
        bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("我的履历")
        title.setObjectName("pageTitle")
        title_box.addWidget(title)
        subtitle = QLabel("一整段自由文本，原文就是唯一事实来源")
        subtitle.setObjectName("hint")
        title_box.addWidget(subtitle)
        bar.addLayout(title_box)
        bar.addStretch(1)

        self.btn_role = QPushButton("切换角色…")
        self.btn_role.setObjectName("secondary")
        self.btn_role.setToolTip("切换、创建或删除角色；每个角色隔离履历、岗位池和文字简历")
        self.btn_role.clicked.connect(self.role_requested)
        bar.addWidget(self.btn_role)

        self.btn_import = QPushButton("从成品简历导入…")
        self.btn_import.setToolTip("支持 .txt / .md / .docx / .pdf；只抽取原文，不自动改写，也不会静默覆盖")
        self.btn_import.clicked.connect(self._on_import)
        bar.addWidget(self.btn_import)

        self.btn_save = QPushButton("保存履历")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(lambda: self._save(silent=False))
        bar.addWidget(self.btn_save)
        root.addLayout(bar)

        tip = QLabel(
            "直接写成一整段即可，不要求按公司、项目或时间线拆分。"
            "AI 只会根据岗位重新组织这份原文，不会增加任何经历、技能或数字。"
        )
        tip.setWordWrap(True)
        tip.setObjectName("hint")
        root.addWidget(tip)

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setPlaceholderText(
            "把你的真实履历整段粘贴到这里，例如：\n\n"
            "姓名、电话、邮箱、所在城市、求职方向……\n"
            "工作经历：公司、职位、时间，以及你实际做过什么、用了什么工具、解决了什么问题。\n"
            "项目经历、教育背景、技能、证书、成果都可以继续写在后面。\n\n"
            "不确定的内容宁可不写；AI 只会优化表达，不会创造事实。"
        )
        self.editor.textChanged.connect(self._on_text_changed)
        root.addWidget(self.editor, 1)

        bottom = QHBoxLayout()
        self.stats = QLabel("0 字")
        self.stats.setObjectName("muted")
        bottom.addWidget(self.stats)
        bottom.addStretch(1)
        self.save_state = QLabel("尚未保存")
        self.save_state.setObjectName("muted")
        bottom.addWidget(self.save_state)
        root.addLayout(bottom)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        header = PageHeader(
            "个人履历",
            "一整段自由文本，不需要按公司、项目或时间线拆分。原文就是唯一事实来源。",
            "PROFILE / SOURCE OF TRUTH",
        )
        self.btn_role = secondary_button("切换角色", "user")
        self.btn_role.setToolTip("切换、创建或删除角色；每个角色隔离履历、岗位池和文字简历")
        self.btn_role.clicked.connect(self.role_requested)
        header.add_action(self.btn_role)
        self.btn_import = secondary_button("从成品简历导入", "upload")
        self.btn_import.setToolTip("支持 .txt / .md / .docx / .pdf；只抽取原文，不自动改写，也不会静默覆盖")
        self.btn_import.clicked.connect(self._on_import)
        header.add_action(self.btn_import)
        self.btn_save = QPushButton("保存履历")
        self.btn_save.setObjectName("primary")
        self.btn_save.setIcon(themed_icon("save", 15))
        self.btn_save.clicked.connect(lambda: self._save(silent=False))
        header.add_action(self.btn_save)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_editor_card())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 280])
        root.addWidget(splitter, 1)

    def _build_editor_card(self) -> Card:
        card = Card()
        card.setObjectName("editorCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("editorToolbar")
        head_row = QHBoxLayout(header)
        head_row.setContentsMargins(16, 11, 14, 10)
        head_row.setSpacing(8)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel("唯一事实来源")
        title.setObjectName("cardTitle")
        copy.addWidget(title)
        tip = QLabel("直接写成完整段落；AI 只重新组织表达，不补充经历、技能、数字或成果。")
        tip.setObjectName("fieldHelp")
        tip.setWordWrap(True)
        copy.addWidget(tip)
        head_row.addLayout(copy, 1)
        self.auto_chip = ChipLabel("自动保存已开启", "success")
        head_row.addWidget(self.auto_chip, 0, Qt.AlignTop)
        layout.addWidget(header)
        layout.addWidget(Divider())

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("profileEditor")
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setPlaceholderText(
            "把你的真实履历整段粘贴到这里，例如：\n\n"
            "姓名、电话、邮箱、所在城市、求职方向……\n"
            "工作经历：公司、职位、时间，以及你实际做过什么、用了什么工具、解决了什么问题。\n"
            "项目经历、教育背景、技能、证书、成果都可以继续写在后面。\n\n"
            "不确定的内容宁可不写；AI 只会优化表达，不会创造事实。"
        )
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, 1)

        footer = QFrame()
        footer.setObjectName("documentFooter")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(14, 7, 14, 7)
        bottom.setSpacing(10)
        self.stats = QLabel("0 字")
        self.stats.setObjectName("muted")
        bottom.addWidget(self.stats)
        bottom.addStretch(1)
        self.save_state = QLabel("尚未保存")
        self.save_state.setObjectName("muted")
        bottom.addWidget(self.save_state)
        layout.addWidget(footer)
        return card

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        fact = Card()
        fact.setObjectName("settingsCard")
        fact_layout = QVBoxLayout(fact)
        fact_layout.setContentsMargins(14, 12, 14, 13)
        fact_layout.setSpacing(7)
        fact_head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(themed_icon("shield", 16).pixmap(16, 16))
        fact_head.addWidget(icon)
        fact_title = QLabel("事实边界")
        fact_title.setObjectName("sectionTitle")
        fact_head.addWidget(fact_title, 1)
        fact_head.addWidget(ChipLabel("已启用", "success"))
        fact_layout.addLayout(fact_head)
        fact_body = QLabel("AI 只会重组这段原文。公司、时间、技能、数字与成果不会被补写或升级。")
        fact_body.setObjectName("fieldHelp")
        fact_body.setWordWrap(True)
        fact_layout.addWidget(fact_body)
        for text in ("原文逐句可追溯", "未确认的信息保持原样", "生成前不调用模型"):
            line = QLabel("✓  " + text)
            line.setObjectName("success")
            fact_layout.addWidget(line)
        layout.addWidget(fact)

        complete = Card()
        complete.setObjectName("settingsCard")
        complete_layout = QVBoxLayout(complete)
        complete_layout.setContentsMargins(14, 12, 14, 13)
        complete_layout.setSpacing(7)
        complete_head = QHBoxLayout()
        complete_title = QLabel("履历完整度")
        complete_title.setObjectName("sectionTitle")
        complete_head.addWidget(complete_title, 1)
        self.complete_value = QLabel("0 / 4")
        self.complete_value.setObjectName("smallValue")
        complete_head.addWidget(self.complete_value)
        complete_layout.addLayout(complete_head)
        self.complete_bar = QProgressBar()
        self.complete_bar.setObjectName("profileProgress")
        self.complete_bar.setRange(0, 4)
        self.complete_bar.setTextVisible(False)
        complete_layout.addWidget(self.complete_bar)
        self.complete_labels = {}
        for key, label in (("contact", "联系方式"), ("experience", "经历"),
                           ("skills", "技能"), ("outcome", "成果")):
            item = QLabel("○  " + label)
            item.setObjectName("muted")
            self.complete_labels[key] = (item, label)
            complete_layout.addWidget(item)
        layout.addWidget(complete)

        source = Card()
        source.setObjectName("settingsCard")
        source_layout = QVBoxLayout(source)
        source_layout.setContentsMargins(14, 12, 14, 13)
        source_layout.setSpacing(6)
        source_head = QHBoxLayout()
        source_title = QLabel("最近导入")
        source_title.setObjectName("sectionTitle")
        source_head.addWidget(source_title, 1)
        source_head.addWidget(ChipLabel("只抽取原文", "neutral"))
        source_layout.addLayout(source_head)
        self.source_file_label = QLabel("尚未导入文件")
        self.source_file_label.setObjectName("smallValue")
        self.source_file_label.setWordWrap(True)
        source_layout.addWidget(self.source_file_label)
        self.source_hint = QLabel("可以直接在左侧编辑；导入不会静默覆盖现有内容。")
        self.source_hint.setObjectName("fieldHelp")
        self.source_hint.setWordWrap(True)
        source_layout.addWidget(self.source_hint)
        layout.addWidget(source)
        layout.addStretch(1)
        return panel

    def _load(self):
        data = profile_text.load_profile_text()
        self._source_file = data.get("source_file") or ""
        self.editor.setPlainText(data.get("text") or "")
        self._last_saved = self.editor.toPlainText()
        self._update_stats()
        self._update_source_card()
        if data.get("migrated_from"):
            self.save_state.setText("已从旧版结构化履历自动迁移")
        elif data.get("updated_at"):
            self.save_state.setText("最近保存：%s" % data["updated_at"])

    def _on_text_changed(self):
        self._update_stats()
        if self._loading:
            return
        self.save_state.setText("有未保存修改…")
        self._save_timer.start()

    def _update_stats(self):
        text = self.editor.toPlainText()
        stats = profile_text.text_stats(text)
        self.stats.setText("%d 字 · %d 行" % (stats["chars"], stats["lines"]))
        checks = {
            "contact": bool(re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+\.\w+", text)),
            "experience": bool(re.search(r"工作经历|任职|公司|项目经历|负责|主导", text)),
            "skills": bool(re.search(r"技能|熟练|工具|技术栈|Halcon|OpenCV|Excel|PLC|C#|Python", text, re.I)),
            "outcome": bool(re.search(r"成果|提升|降低|节省|交付|\d+%|\d+\s*(个|项|套|台|年)", text)),
        }
        if hasattr(self, "complete_labels"):
            score = 0
            for key, (label, text_value) in self.complete_labels.items():
                hit = checks.get(key, False)
                score += 1 if hit else 0
                label.setText(("✓  " if hit else "○  ") + text_value)
                label.setObjectName("success" if hit else "muted")
                label.style().unpolish(label)
                label.style().polish(label)
            self.complete_bar.setValue(score)
            self.complete_value.setText("%d / 4" % score)

    def _update_source_card(self):
        if not hasattr(self, "source_file_label"):
            return
        if self._source_file:
            path = Path(self._source_file)
            self.source_file_label.setText(path.name)
            self.source_file_label.setToolTip(self._source_file)
            self.source_hint.setText("已抽取原文；内容是否准确仍需你核对。")
        else:
            self.source_file_label.setText("尚未导入文件")
            self.source_file_label.setToolTip("")
            self.source_hint.setText("可以直接在左侧编辑；导入不会静默覆盖现有内容。")

    @property
    def current_text(self) -> str:
        return self.editor.toPlainText()

    def save_now(self, silent: bool = False) -> bool:
        return self._save(silent=silent)

    def suspend_saving(self):
        """Stop auto-save before an explicit local-data reset."""
        self._save_timer.stop()
        self._loading = True

    def _save(self, silent: bool = False) -> bool:
        self._save_timer.stop()
        text = self.editor.toPlainText()
        if text == self._last_saved:
            if not silent:
                self.status.emit("履历没有变化")
            return True
        try:
            data = profile_text.save_profile_text(text, source_file=self._source_file)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            self.status.emit("履历保存失败")
            return False
        self._last_saved = text
        self.save_state.setText("已保存：%s" % data.get("updated_at", ""))
        self.status.emit("个人履历已保存（%d 字）" % len(text))
        self.profile_saved.emit()
        return True

    @property
    def has_unsaved(self) -> bool:
        return self.editor.toPlainText() != self._last_saved

    def reload_for_profile(self):
        """切换角色时丢弃旧编辑器状态，重新加载新角色履历。"""
        self._save_timer.stop()
        self._loading = True
        self._load()
        self._loading = False

    def set_role_name(self, name: str):
        text = str(name or "").strip()
        self.btn_role.setText("切换角色")
        self.btn_role.setToolTip(
            "当前角色：%s\n点击切换、创建或删除角色工作区" % text
            if text else "切换、创建或删除角色工作区"
        )

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择成品简历", "", "简历文件 (*.txt *.md *.docx *.pdf);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            text = read_document_text(path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", "无法读取该文件：\n%s" % exc)
            self.status.emit("成品简历读取失败")
            return
        text = str(text or "").strip()
        if not text:
            QMessageBox.warning(self, "没有内容", "没有从文件里提取到文字，可能是扫描版 PDF。")
            return

        existing = self.editor.toPlainText().strip()
        if existing:
            box = QMessageBox(self)
            box.setWindowTitle("导入方式")
            box.setText("当前已有履历内容，请选择导入方式。")
            replace_btn = box.addButton("替换现有内容", QMessageBox.AcceptRole)
            append_btn = box.addButton("追加到末尾", QMessageBox.ActionRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.exec_()
            clicked = box.clickedButton()
            if clicked is replace_btn:
                self.editor.setPlainText(text)
            elif clicked is append_btn:
                self.editor.setPlainText(existing + "\n\n" + text)
            else:
                return
        else:
            self.editor.setPlainText(text)

        self._source_file = path
        self._save(silent=True)
        self._update_source_card()
        self.save_state.setText("已导入：%s" % Path(path).name)
        self.status.emit("成品简历已导入，共 %d 字；请核对原文" % len(text))
        QMessageBox.information(
            self, "导入完成",
            "已提取原文并保存。\n\n请注意：导入只做文字抽取，不代表内容已核实；"
            "请检查其中的公司、职位、时间、技能和数字是否准确。",
        )
