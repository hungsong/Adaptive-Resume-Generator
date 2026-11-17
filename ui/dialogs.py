# -*- coding: utf-8 -*-
"""对话框集合：履历条目编辑 / 旧简历导入 / 设置 / 简历内容编辑 / 问题报告。"""
from __future__ import annotations

import copy

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyledItemDelegate,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core import models
from core.config import api_config, load_config, save_config
from core.llm import LLMClient
from core.readers import read_document_text
from ui.worker import Worker
from ui.widgets import NoWheelDoubleSpinBox, NoWheelSpinBox

ITEM_ROLE = Qt.UserRole


class EntryDialog(QDialog):
    """按 SECTION_SPECS 自动生成表单，编辑一条履历条目。"""

    def __init__(self, spec: dict, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.spec = spec
        entry = entry or {}
        self.setWindowTitle(("编辑 " if entry else "新增 ") + spec["title"])
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._inputs = {}
        for key, label in spec["item_fields"]:
            edit = QLineEdit(str(entry.get(key, "") or ""))
            self._inputs[key] = edit
            form.addRow(label + "：", edit)
        layout.addLayout(form)

        self._detail = None
        if spec["kind"] == "timeline":
            layout.addWidget(QLabel(spec.get("detail_label") or "细节（每行一条）"))
            self._detail = QPlainTextEdit(str(entry.get("raw", "") or ""))
            self._detail.setMinimumHeight(150)
            self._detail.setPlaceholderText(
                "一行写一条，写你自己的原话即可，例如：\n"
                "使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯"
            )
            layout.addWidget(self._detail)

        self._confirmed = QCheckBox("这条信息我已确认属实")
        self._confirmed.setChecked(bool(entry.get("confirmed", True)))
        layout.addWidget(self._confirmed)

        hint = QLabel("AI 只做表达优化，不会新增事实；不确定的内容请留空。")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> dict:
        out = {key: widget.text().strip() for key, widget in self._inputs.items()}
        if self._detail is not None:
            out["raw"] = self._detail.toPlainText().strip()
        out["confirmed"] = self._confirmed.isChecked()
        return out


class ImportResumeDialog(QDialog):
    """一键粘贴分析：粘贴旧简历全文（或从文件读取），交给 AI 逆向成主履历。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入旧简历（一键粘贴分析）")
        self.resize(760, 560)
        layout = QVBoxLayout(self)

        tip = QLabel(
            "把旧简历内容整段粘贴到下面（也可以直接选 .docx / .pdf / .txt 文件）。\n"
            "解析出来的内容会全部标记为「待确认」，请你逐条核对后再用于生成简历。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(
            "例如：\n张三  13800000000  苏州\n\n工作经历\n2020.03 - 2023.05  某某自动化  视觉工程师\n"
            "- 使用机器视觉系统完成客户现场设备调试，涉及相机、光源、PLC、TCP/IP 通讯"
        )
        layout.addWidget(self.text, 1)

        row = QHBoxLayout()
        pick = QPushButton("从文件读取…")
        pick.clicked.connect(self._pick_file)
        clear = QPushButton("清空")
        clear.clicked.connect(self.text.clear)
        row.addWidget(pick)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("开始解析")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择旧简历文件", "", "简历文件 (*.txt *.md *.docx *.pdf);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            content = read_document_text(path)
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))
            return
        self.text.setPlainText(content)

    def content(self) -> str:
        return self.text.toPlainText().strip()


class SettingsDialog(QDialog):
    """接口设置：换模型 / 换服务商只改这里。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("接口设置")
        self.setMinimumWidth(560)
        cfg = load_config()
        api = api_config(cfg)
        self._cfg = cfg

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.base_url = QLineEdit(api["base_url"])
        self.model = QLineEdit(api["model"])
        self.api_key = QLineEdit(api["api_key"])
        self.api_key.setEchoMode(QLineEdit.Password)
        self.show_key = QCheckBox("显示 Key")
        self.show_key.toggled.connect(
            lambda on: self.api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        self.timeout = NoWheelSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setValue(int(api["timeout"]))
        self.max_tokens = NoWheelSpinBox()
        self.max_tokens.setRange(512, 32000)
        self.max_tokens.setValue(int(api["max_tokens"]))
        self.temperature = NoWheelDoubleSpinBox()
        self.temperature.setRange(0.0, 1.5)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(float(api["temperature"]))

        form.addRow("接口地址：", self.base_url)
        form.addRow("模型名称：", self.model)
        form.addRow("API Key：", self.api_key)
        form.addRow("", self.show_key)
        form.addRow("超时（秒）：", self.timeout)
        form.addRow("最大输出 token：", self.max_tokens)
        form.addRow("温度：", self.temperature)
        layout.addLayout(form)

        note = QLabel(
            "默认适配 DeepSeek（https://api.deepseek.com + deepseek-chat）。\n"
            "换成 OpenAI 或其它兼容端点时，只改接口地址与模型名即可。\n"
            "Key 保存在本机 config.json（已排除在 git 备份之外）。"
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test)
        row.addWidget(self.test_btn)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._worker = None

    def _current_api(self) -> dict:
        return {
            "provider": "custom",
            "base_url": self.base_url.text().strip(),
            "model": self.model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "timeout": self.timeout.value(),
            "max_tokens": self.max_tokens.value(),
            "temperature": self.temperature.value(),
        }

    def _test(self):
        self.test_btn.setEnabled(False)
        self.result_label.setText("正在测试…")
        client = LLMClient(self._current_api())
        self._worker = Worker(lambda progress: client.test_connection(), self)
        self._worker.done.connect(self._on_test_ok)
        self._worker.failed.connect(self._on_test_fail)
        self._worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        self._worker.start()

    def _on_test_ok(self, text):
        self.result_label.setText("连接成功，模型回复：%s" % text)
        self.result_label.setObjectName("success")

    def _on_test_fail(self, message):
        self.result_label.setText("连接失败：%s" % message)
        self.result_label.setObjectName("dangerText")

    def _save_and_close(self):
        cfg = copy.deepcopy(self._cfg)
        cfg.setdefault("api", {})
        cfg["api"].update(self._current_api())
        save_config(cfg)
        self.accept()


class _EditableColumnDelegate(QStyledItemDelegate):
    """只允许编辑指定列，避免误改结构列。"""

    def __init__(self, column: int, parent=None):
        super().__init__(parent)
        self._column = column

    def createEditor(self, parent, option, index):
        if index.column() != self._column:
            return None
        return super().createEditor(parent, option, index)


class ResumeEditorDialog(QDialog):
    """直接修改生成出来的简历：AI 的产物必须可改、可删。"""

    def __init__(self, doc: dict, parent=None):
        super().__init__(parent)
        self.doc = copy.deepcopy(doc)
        self.setWindowTitle("编辑简历内容")
        self.resize(940, 640)
        layout = QVBoxLayout(self)
        tip = QLabel("双击「内容」列即可修改；可删除 / 上下移动要点。保存后会重新做一次真实性校验。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["结构", "内容（双击编辑）"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setItemDelegate(_EditableColumnDelegate(1, self.tree))
        self.tree.setEditTriggers(
            QTreeWidget.DoubleClicked | QTreeWidget.EditKeyPressed | QTreeWidget.SelectedClicked
        )
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        for text, slot in (
            ("添加要点", self._add_bullet),
            ("删除选中", self._remove_selected),
            ("上移", lambda: self._move(-1)),
            ("下移", lambda: self._move(1)),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------ 构建
    def _load(self):
        self.tree.clear()
        summary = QTreeWidgetItem(["个人简介", str(self.doc.get("summary") or "")])
        summary.setData(0, ITEM_ROLE, ("summary",))
        self.tree.addTopLevelItem(summary)

        for sec in self.doc.get("sections") or []:
            key = sec.get("key")
            node = QTreeWidgetItem(["▍ %s" % (sec.get("title") or ""), sec.get("title") or ""])
            node.setData(0, ITEM_ROLE, ("section", key))
            for item in sec.get("items") or []:
                if key in ("skills", "certificates", "achievements"):
                    text = item.get("text") if isinstance(item, dict) else str(item)
                    child = QTreeWidgetItem(["·", str(text or "")])
                    child.setData(0, ITEM_ROLE, ("item", key, {"text": text, "evidence_ids": item.get("evidence_ids", []) if isinstance(item, dict) else []}))
                    node.addChild(child)
                    continue
                org = item.get("org") or ""
                role = item.get("role") or ""
                period = " - ".join([p for p in (item.get("start"), item.get("end")) if p])
                head = " ".join([p for p in (org, role) if p]) or "（未命名）"
                child = QTreeWidgetItem(["%s   %s" % (head, period), ""])
                child.setData(0, ITEM_ROLE, ("item", key, copy.deepcopy(item)))
                for bullet in item.get("bullets") or []:
                    text = bullet.get("text") if isinstance(bullet, dict) else str(bullet)
                    evidence = bullet.get("evidence_ids", []) if isinstance(bullet, dict) else []
                    bnode = QTreeWidgetItem(["·", str(text or "")])
                    bnode.setData(0, ITEM_ROLE, ("bullet", list(evidence or [])))
                    child.addChild(bnode)
                node.addChild(child)
            self.tree.addTopLevelItem(node)
            node.setExpanded(True)

    # ------------------------------------------------------------ 操作
    def _current(self):
        return self.tree.currentItem()

    def _add_bullet(self):
        node = self._current()
        if node is None:
            return
        data = node.data(0, ITEM_ROLE) or ()
        if data and data[0] == "bullet":
            node = node.parent()
        elif data and data[0] == "section":
            QMessageBox.information(self, "提示", "请先选中具体的一条经历，再添加要点。")
            return
        if node is None:
            return
        parent_data = node.data(0, ITEM_ROLE) or ()
        if len(parent_data) < 2 or parent_data[1] in ("skills", "certificates", "achievements"):
            QMessageBox.information(self, "提示", "该章节不支持添加要点。")
            return
        bullet = QTreeWidgetItem(["·", "新要点（请修改）"])
        bullet.setData(0, ITEM_ROLE, ("bullet", []))
        node.addChild(bullet)
        node.setExpanded(True)
        self.tree.setCurrentItem(bullet)

    def _remove_selected(self):
        node = self._current()
        if node is None:
            return
        data = node.data(0, ITEM_ROLE) or ()
        if data and data[0] == "section":
            QMessageBox.information(self, "提示", "章节不能删除；如需精简内容，请删除章节里的条目或要点。")
            return
        parent = node.parent()
        if parent is None:
            QMessageBox.information(self, "提示", "个人简介不能删除，可以直接清空内容。")
            return
        parent.removeChild(node)

    def _move(self, step: int):
        node = self._current()
        if node is None:
            return
        parent = node.parent()
        if parent is None:
            return
        index = parent.indexOfChild(node)
        target = index + step
        if not (0 <= target < parent.childCount()):
            return
        parent.takeChild(index)
        parent.insertChild(target, node)
        self.tree.setCurrentItem(node)

    # ------------------------------------------------------------ 结果
    def result_doc(self) -> dict:
        doc = copy.deepcopy(self.doc)
        doc["summary"] = ""
        doc["sections"] = []
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            data = node.data(0, ITEM_ROLE) or ()
            kind = data[0] if data else ""
            if kind == "summary":
                doc["summary"] = node.text(1).strip()
                continue
            if kind != "section":
                continue
            key = data[1]
            title = node.text(1).strip() or models.RESUME_SECTION_TITLES.get(key, key)
            items = []
            for j in range(node.childCount()):
                inode = node.child(j)
                idata = inode.data(0, ITEM_ROLE) or ()
                if len(idata) < 3:
                    continue
                item = copy.deepcopy(idata[2])
                if key in ("skills", "certificates", "achievements"):
                    text = inode.text(1).strip()
                    if not text:
                        continue
                    item["text"] = text
                else:
                    bullets = []
                    for k in range(inode.childCount()):
                        bnode = inode.child(k)
                        text = bnode.text(1).strip()
                        if not text:
                            continue
                        bdata = bnode.data(0, ITEM_ROLE) or ()
                        evidence = list(bdata[1]) if len(bdata) > 1 else []
                        bullets.append({"text": text, "evidence_ids": evidence, "flagged": False})
                    item["bullets"] = bullets
                items.append(item)
            if items:
                doc["sections"].append({"key": key, "title": title, "items": items})
        doc.pop("summary_flagged", None)
        return doc


class IssueReportDialog(QDialog):
    """真实性校验报告：告诉用户哪些地方被拦截、哪些地方需要自己确认。"""

    def __init__(self, title: str, issues: list, parent=None, note: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        if note:
            label = QLabel(note)
            label.setWordWrap(True)
            layout.addWidget(label)

        errors = [i for i in issues if i.get("level") == "error"]
        warns = [i for i in issues if i.get("level") == "warn"]
        self._plain = "\n".join(
            "[%s] %s" % (i.get("kind", ""), i.get("message", "")) for i in issues
        ) or "未发现真实性问题。"

        view = QTextBrowser()
        parts = []
        if not issues:
            parts.append('<p style="color:#2e7d32;">未发现真实性问题，内容与主履历一致。</p>')
        else:
            if errors:
                parts.append('<p style="color:#c62828;font-weight:bold;">被拦截（已尝试自动修正）：%d 条</p><ul>' % len(errors))
                parts += ['<li style="color:#c62828;">%s</li>' % i.get("message", "") for i in errors]
                parts.append("</ul>")
            if warns:
                parts.append('<p style="color:#b26a00;font-weight:bold;">需要你确认：%d 条</p><ul>' % len(warns))
                parts += ['<li style="color:#b26a00;">%s</li>' % i.get("message", "") for i in warns]
                parts.append("</ul>")
        view.setHtml("".join(parts))
        layout.addWidget(view, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("知道了")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def plain_text(self) -> str:
        return self._plain
