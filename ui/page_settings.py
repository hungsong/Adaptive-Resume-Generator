# -*- coding: utf-8 -*-
"""Settings workspace: model endpoint, appearance, browser and local data."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core import profiles
from core.config import LOG_DIR, api_config, load_config, save_config
from core.llm import LLMClient
from ui.browser import detect_browsers, save_browser_choice
from ui.components import (
    Card, Divider, ElidedLabel, PageHeader, primary_button, secondary_button,
)
from ui.widgets import NoWheelComboBox
from ui.icons import themed_icon
from ui.worker import Worker


class _PathRow(QFrame):
    open_requested = pyqtSignal(str)

    def __init__(self, label: str, path: str, parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.setObjectName("pathRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 5, 7)
        row.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(label)
        title.setObjectName("smallLabel")
        value = ElidedLabel(self.path)
        value.setObjectName("smallValue")
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        copy.addWidget(title)
        copy.addWidget(value)
        row.addLayout(copy, 1)
        button = secondary_button("打开", "folder")
        button.setFixedHeight(28)
        button.clicked.connect(lambda: self.open_requested.emit(self.path))
        row.addWidget(button)


class SettingsPage(QWidget):
    status = pyqtSignal(str)
    theme_changed = pyqtSignal(str)
    open_path_requested = pyqtSignal(str)
    clear_data_requested = pyqtSignal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._cfg = load_config()
        self._worker = None
        self._theme_group = QButtonGroup(self)
        self._theme_group.setExclusive(True)
        self._build()
        self.reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "设置",
            "模型接口、界面与本地数据。所有内容只保存在这台电脑。",
            "PREFERENCES / LOCAL ONLY",
        )
        self.btn_save = primary_button("保存设置", "save")
        self.btn_save.clicked.connect(self.save)
        self.header.add_action(self.btn_save)
        root.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("settingsHolder")
        content = QVBoxLayout(holder)
        content.setContentsMargins(0, 0, 8, 12)
        content.setSpacing(12)
        content.addWidget(self._build_model_card())

        two_col = QHBoxLayout()
        two_col.setSpacing(12)
        two_col.addWidget(self._build_appearance_card(), 1)
        two_col.addWidget(self._build_browser_card(), 1)
        content.addLayout(two_col)
        content.addWidget(self._build_local_card())
        content.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

    def _build_model_card(self) -> Card:
        card = Card()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 16)
        layout.setSpacing(12)
        head, self.connection_chip = self._card_header(
            "key", "模型接口", "兼容 OpenAI 协议；默认使用 DeepSeek。"
        )
        layout.addLayout(head)

        grid_top = QGridLayout()
        grid_top.setHorizontalSpacing(10)
        grid_top.setVerticalSpacing(6)
        self.base_url = QLineEdit()
        self.model = QLineEdit()
        grid_top.addWidget(self._field_label("接口地址"), 0, 0)
        grid_top.addWidget(self._field_label("模型"), 0, 1)
        grid_top.addWidget(self.base_url, 1, 0)
        grid_top.addWidget(self.model, 1, 1)
        layout.addLayout(grid_top)

        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-…")
        key_row.addWidget(self.api_key, 1)
        self.btn_show_key = secondary_button("显示", "key")
        self.btn_show_key.setCheckable(True)
        self.btn_show_key.setFixedWidth(68)
        self.btn_show_key.toggled.connect(self._toggle_key)
        key_row.addWidget(self.btn_show_key)
        key_box = QVBoxLayout()
        key_box.setSpacing(6)
        key_box.addWidget(self._field_label("API Key"))
        key_box.addLayout(key_row)
        layout.addLayout(key_box)

        advanced = QGridLayout()
        advanced.setHorizontalSpacing(10)
        advanced.setVerticalSpacing(6)
        self.timeout = QLineEdit()
        self.max_tokens = QLineEdit()
        self.temperature = QLineEdit()
        for col, (label, widget) in enumerate((
            ("超时（秒）", self.timeout),
            ("最大输出 token", self.max_tokens),
            ("温度", self.temperature),
        )):
            advanced.addWidget(self._field_label(label), 0, col)
            advanced.addWidget(widget, 1, col)
        layout.addLayout(advanced)
        note = QLabel("Key 只写入本机 config.json，不会出现在日志、截图或开源仓库中。")
        note.setObjectName("fieldHelp")
        layout.addWidget(note)

        action = QHBoxLayout()
        self.test_result = QLabel("")
        self.test_result.setObjectName("fieldHelp")
        self.test_result.setWordWrap(True)
        action.addWidget(self.test_result, 1)
        self.btn_test = secondary_button("测试连接")
        self.btn_test.clicked.connect(self._test_connection)
        action.addWidget(self.btn_test)
        layout.addLayout(action)
        return card

    def _build_appearance_card(self) -> Card:
        card = Card()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 16)
        layout.setSpacing(13)
        head, _ = self._card_header("monitor", "外观", "主题会立即应用到所有页面。")
        layout.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(7)
        for value, label, icon_name in (
            ("system", "跟随系统", "monitor"),
            ("light", "浅色", "sun"),
            ("dark", "深色", "moon"),
        ):
            button = QPushButton(label)
            button.setObjectName("themeOption")
            button.setCheckable(True)
            button.setProperty("themeValue", value)
            button.setIcon(themed_icon(icon_name, 17))
            button.setToolTip({"system": "使用 Windows 设置", "light": "明亮、清晰", "dark": "低光环境"}[value])
            button.clicked.connect(lambda _checked=False, v=value: self._choose_theme(v))
            self._theme_group.addButton(button)
            row.addWidget(button, 1)
        layout.addLayout(row)
        hint = QLabel("深色主题使用低对比边框，长文本和岗位状态保持可读。")
        hint.setObjectName("fieldHelp")
        layout.addWidget(hint)
        return card

    def _build_browser_card(self) -> Card:
        card = Card()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 16)
        layout.setSpacing(12)
        head, self.bridge_chip = self._card_header(
            "briefcase", "浏览器采集", "本地桥接只监听 127.0.0.1，不暴露到局域网。"
        )
        layout.addLayout(head)
        layout.addWidget(self._field_label("用于打开 BOSS 的浏览器"))
        self.browser_combo = NoWheelComboBox()
        layout.addWidget(self.browser_combo)
        self.browser_hint = QLabel("选择后会记住，下次打开岗位搜索页继续使用。")
        self.browser_hint.setObjectName("fieldHelp")
        self.browser_hint.setWordWrap(True)
        layout.addWidget(self.browser_hint)
        info = QFrame()
        info.setObjectName("infoGrid")
        info_grid = QGridLayout(info)
        info_grid.setContentsMargins(11, 9, 11, 9)
        info_grid.setHorizontalSpacing(14)
        info_grid.setVerticalSpacing(3)
        self.bridge_port = QLabel("8765")
        self.browser_state = QLabel("等待浏览器页面连接")
        for col, (label, value) in enumerate((
            ("当前端口", self.bridge_port), ("采集状态", self.browser_state)
        )):
            small = QLabel(label)
            small.setObjectName("smallLabel")
            info_grid.addWidget(small, 0, col)
            value.setObjectName("smallValue")
            info_grid.addWidget(value, 1, col)
        layout.addWidget(info)
        return card

    def _build_local_card(self) -> Card:
        card = Card()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 15, 17, 16)
        layout.setSpacing(10)
        head, _ = self._card_header(
            "database", "本地数据", "角色、岗位、评分和简历按角色隔离保存。"
        )
        layout.addLayout(head)
        self.path_grid = QGridLayout()
        self.path_grid.setHorizontalSpacing(10)
        self.path_grid.setVerticalSpacing(8)
        self.path_grid.setColumnStretch(0, 1)
        self.path_grid.setColumnStretch(1, 1)
        layout.addLayout(self.path_grid)
        layout.addWidget(Divider())

        danger = QFrame()
        danger.setObjectName("dangerZone")
        danger_layout = QHBoxLayout(danger)
        danger_layout.setContentsMargins(12, 10, 10, 10)
        danger_layout.setSpacing(12)
        danger_icon = QLabel()
        danger_icon.setPixmap(themed_icon("alert", 18).pixmap(18, 18))
        danger_icon.setFixedSize(20, 20)
        danger_layout.addWidget(danger_icon, 0, Qt.AlignTop)
        danger_copy = QVBoxLayout()
        danger_copy.setSpacing(2)
        danger_title = QLabel("清空所有本地数据")
        danger_title.setObjectName("dangerZoneTitle")
        danger_copy.addWidget(danger_title)
        danger_body = QLabel(
            "永久删除全部角色、履历、岗位池、评分、文字简历、备份与日志。"
            "API Key 默认保留，可在确认弹窗中选择一并删除。"
        )
        danger_body.setObjectName("dangerZoneBody")
        danger_body.setWordWrap(True)
        danger_copy.addWidget(danger_body)
        danger_layout.addLayout(danger_copy, 1)
        self.btn_clear_data = QPushButton("清空所有本地数据")
        self.btn_clear_data.setObjectName("danger")
        self.btn_clear_data.setIcon(themed_icon("trash", 15))
        self.btn_clear_data.setToolTip("清空后不可恢复，会重新进入首次创建角色流程")
        self.btn_clear_data.clicked.connect(self.clear_data_requested.emit)
        danger_layout.addWidget(self.btn_clear_data, 0, Qt.AlignVCenter)
        layout.addWidget(danger)
        return card

    def _card_header(self, icon_name: str, title: str, body: str):
        row = QHBoxLayout()
        row.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(themed_icon(icon_name, 17).pixmap(17, 17))
        icon.setFixedSize(19, 19)
        row.addWidget(icon, 0, Qt.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("settingsTitle")
        copy.addWidget(title_label)
        body_label = QLabel(body)
        body_label.setObjectName("settingsBody")
        body_label.setWordWrap(True)
        copy.addWidget(body_label)
        row.addLayout(copy, 1)
        chip = QLabel("本地配置")
        chip.setObjectName("chipNeutral")
        row.addWidget(chip, 0, Qt.AlignTop)
        return row, chip

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _toggle_key(self, checked: bool):
        self.api_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.btn_show_key.setText("隐藏" if checked else "显示")

    def _choose_theme(self, value: str):
        self._save_theme_local(value)
        self.theme_changed.emit(value)

    def _save_theme_local(self, value: str):
        cfg = load_config()
        cfg.setdefault("ui", {})["theme"] = value
        save_config(cfg)
        self._cfg = cfg

    def set_theme(self, value: str):
        for button in self._theme_group.buttons():
            button.setChecked(button.property("themeValue") == value)

    def set_bridge_status(self, connected: bool, port: int | None = None):
        if connected:
            self.bridge_chip.setText("已连接")
            self.bridge_chip.setObjectName("chipSuccess")
            self.browser_state.setText("采集扩展已连接")
        else:
            self.bridge_chip.setText("未连接")
            self.bridge_chip.setObjectName("chipWarning")
            self.browser_state.setText("等待浏览器页面连接")
        self.bridge_chip.style().unpolish(self.bridge_chip)
        self.bridge_chip.style().polish(self.bridge_chip)
        if port:
            self.bridge_port.setText(str(port))

    def reload(self):
        self._cfg = load_config()
        api = api_config(self._cfg)
        self.base_url.setText(api["base_url"])
        self.model.setText(api["model"])
        self.api_key.setText(api["api_key"])
        self.timeout.setText(str(api["timeout"]))
        self.max_tokens.setText(str(api["max_tokens"]))
        self.temperature.setText(str(api["temperature"]))
        self.connection_chip.setText("已配置" if api["api_key"] else "未配置")
        self.connection_chip.setObjectName("chipSuccess" if api["api_key"] else "chipWarning")
        self.connection_chip.style().unpolish(self.connection_chip)
        self.connection_chip.style().polish(self.connection_chip)
        self.set_theme(str((self._cfg.get("ui") or {}).get("theme") or "system"))
        self._reload_browsers()
        self._reload_paths()

    def _reload_browsers(self):
        current = str((self._cfg.get("ui") or {}).get("browser_key") or "system")
        self.browser_combo.clear()
        options = detect_browsers()
        for item in options:
            self.browser_combo.addItem(item["name"], item)
        index = next((i for i, item in enumerate(options) if item["key"] == current), 0)
        self.browser_combo.setCurrentIndex(index)

    def _reload_paths(self):
        while self.path_grid.count():
            item = self.path_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        active = profiles.active_profile()
        if active:
            paths = profiles.profile_paths(active["id"])
            values = (
                ("当前角色目录", str(paths["base"])),
                ("个人履历文件", str(paths["profile_text"])),
                ("岗位池目录", str(paths["jobs_dir"])),
                ("运行日志", str(LOG_DIR)),
            )
        else:
            values = (("应用数据目录", "尚未选择角色"), ("运行日志", str(LOG_DIR)))
        for index, (label, path) in enumerate(values):
            row = _PathRow(label, path)
            row.open_requested.connect(self.open_path_requested.emit)
            self.path_grid.addWidget(row, index // 2, index % 2)

    def save(self, notify: bool = True) -> bool:
        try:
            timeout = max(10, min(600, int(float(self.timeout.text().strip() or "120"))))
            max_tokens = max(512, min(32000, int(float(self.max_tokens.text().strip() or "4096"))))
            temperature = max(0.0, min(1.5, float(self.temperature.text().strip() or "0.3")))
        except ValueError:
            QMessageBox.warning(self, "格式错误", "超时、最大 token 和温度必须是数字。")
            return False
        cfg = load_config()
        cfg.setdefault("api", {}).update({
            "provider": "custom",
            "base_url": self.base_url.text().strip(),
            "model": self.model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "timeout": timeout,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        choice = self.browser_combo.currentData() or {"key": "system", "path": ""}
        cfg.setdefault("ui", {}).update({
            "browser_key": choice.get("key") or "system",
            "browser_path": choice.get("path") or "",
        })
        try:
            save_config(cfg)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        self._cfg = cfg
        save_browser_choice(choice.get("key") or "system", choice.get("path") or "")
        self.ctx.reload()
        self.status.emit("设置已保存")
        if notify:
            QMessageBox.information(self, "已保存", "模型接口与浏览器设置已保存到本机。")
        return True

    def _test_connection(self):
        self.btn_test.setEnabled(False)
        self.test_result.setText("正在测试连接…")
        api = {
            "provider": "custom",
            "base_url": self.base_url.text().strip(),
            "model": self.model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "timeout": 30,
            "max_tokens": 64,
            "temperature": 0.1,
        }
        client = LLMClient(api)
        self._worker = Worker(lambda progress: client.test_connection(), self)
        self._worker.done.connect(self._on_test_ok)
        self._worker.failed.connect(self._on_test_fail)
        self._worker.finished.connect(lambda: self.btn_test.setEnabled(True))
        self._worker.start()

    def _on_test_ok(self, text):
        self.test_result.setText("连接成功：%s" % str(text or "")[:100])

    def _on_test_fail(self, message):
        self.test_result.setText("连接失败：%s" % message)
