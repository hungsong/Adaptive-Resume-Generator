# -*- coding: utf-8 -*-
"""页面 2：岗位池、意向配置与一键流水线。"""
from __future__ import annotations

import datetime as _dt
from urllib.parse import quote

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QShortcut, QSizePolicy, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core import intent, job_db, jobs as job_store, live, pipeline, profile_text, tailor_text
from ui import browser
from ui.components import (
    Card, ChipLabel, Divider, ElidedLabel, PageHeader, ghost_button,
    secondary_button,
)
from ui.icons import themed_icon
from ui.widgets import NoWheelSpinBox
from ui.worker import Worker, WorkerKeeper


STATUS_LABELS = {
    "unscored": "待评分",
    "recommended": "推荐",
    "review": "复核",
    "rejected": "淘汰",
    "needs_detail": "详情不足",
    "error": "评分失败",
}

STRENGTH_LABELS = intent.REWRITE_STRENGTH_LABELS


def _dimension_text(job: dict) -> str:
    intent_result = job.get("intent") or {}
    lines = []
    if intent_result.get("reason"):
        lines.append("结论：%s" % intent_result["reason"])
    dims = intent_result.get("dimensions") or {}
    for key, label in intent.DIMENSION_LABELS.items():
        item = dims.get(key) or {}
        lines.append("%s：%s 分  %s" % (label, item.get("score", "-"), item.get("reason", "")))
    gate = intent_result.get("gate") or {}
    if gate.get("notes"):
        lines += ["", "本地门槛提示："] + ["- " + str(x) for x in gate["notes"]]
    if gate.get("reasons"):
        lines += ["", "本地门槛拦截："] + ["- " + str(x) for x in gate["reasons"]]
    risks = intent_result.get("risks") or []
    if risks:
        lines += ["", "风险与缺口："] + ["- " + str(x) for x in risks]
    if intent_result.get("errors"):
        lines += ["", "状态：%s" % intent_result.get("status", "")]
    return "\n".join(lines) or "尚未评分。"


class JobDetailDialog(QDialog):
    def __init__(self, job: dict, parent=None):
        super().__init__(parent)
        self.job = job
        self.setWindowTitle(job_store.display_name(job))
        self.resize(900, 720)
        root = QVBoxLayout(self)
        title = QLabel(job_store.display_name(job))
        title.setObjectName("pageTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        intent_result = job.get("intent") or {}
        form = QFormLayout()
        form.addRow("城市：", QLabel(job.get("city") or "未识别"))
        form.addRow("薪资：", QLabel(job.get("salary") or "未识别"))
        form.addRow("经验/学历：", QLabel(" / ".join(filter(None, [job.get("experience"), job.get("education")])) or "未识别"))
        form.addRow("行业/规模：", QLabel(" / ".join(filter(None, [
            job.get("industry"), job.get("company_scale"),
        ])) or "未识别"))
        form.addRow("扩展参考分：", QLabel(str(job.get("extension_score") or "-")))
        form.addRow("意向状态：", QLabel("%s  %s 分" % (
            STATUS_LABELS.get(intent_result.get("status"), "待评分"), intent_result.get("score", "-")
        )))
        root.addLayout(form)

        tabs = QTabWidget()
        jd = QPlainTextEdit()
        jd.setReadOnly(True)
        jd.setPlainText(job.get("jd_text") or "（没有完整 JD，请重新采集）")
        tabs.addTab(jd, "岗位详情")
        analysis = QPlainTextEdit()
        analysis.setReadOnly(True)
        analysis.setPlainText(_dimension_text(job))
        tabs.addTab(analysis, "意向分析")
        output = QPlainTextEdit()
        output.setReadOnly(True)
        tailored = job.get("tailored") or {}
        output.setPlainText(tailored.get("text") or "尚未生成文字简历。")
        tabs.addTab(output, "文字简历")
        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        if job.get("url"):
            open_btn = buttons.addButton("打开原岗位", QDialogButtonBox.ActionRole)
            open_btn.setObjectName("ghost")
            open_btn.clicked.connect(lambda: browser.open_external_url(job["url"]))
        root.addWidget(buttons)


class JobPoolPage(QWidget):
    status = pyqtSignal(str)
    progress = pyqtSignal(int, str)
    outputs_ready = pyqtSignal()
    open_output_requested = pyqtSignal(str)

    def __init__(self, ctx, profile_provider=None, bridge=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.profile_provider = profile_provider
        self.bridge = bridge
        self.keeper = WorkerKeeper()
        self.jobs = []
        self._rows = []
        self._busy = False
        self._live_worker = None
        self._live_job = None
        self._bridge_jobs_queue = []
        self._scan_running = False
        self._scan_id = ""
        self._scan_criteria = {}
        self._scan_profile = ""
        self._scan_auto_tailor = False
        self._scan_expected = 0
        self._scan_seen = 0
        self._scan_processed = 0
        self._scan_recommended = 0
        self._scan_tailored = 0
        self._scan_failures = []
        self._scan_pending_finish = None
        self._scan_finalized = True
        self._criteria_widgets = {}
        self.hidden_ids = set()
        self._selected_job_ids = set()
        self._show_hidden = False
        self._filling_table = False
        self._inspector_job = None
        self._score_rows = {}
        self._build()
        if self.bridge:
            self.bridge.connection_changed.connect(self._on_bridge_connection)
            self.bridge.event_received.connect(self._on_bridge_event)
            self.bridge.failed.connect(self._on_bridge_failed)
            self._on_bridge_connection(self.bridge.connected, "已连接采集扩展")
        else:
            self._on_bridge_connection(False, "未连接采集扩展")
        self._load_criteria()
        self.refresh()

    # ------------------------------------------------------------ 构建
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.header = PageHeader(
            "岗位工作台",
            "遍历、评分、筛选，再为值得投入的岗位生成文字简历。",
            "JOB WORKBENCH / PIPELINE",
        )
        self.btn_import = secondary_button("导入 JSON", "upload")
        self.btn_import.setToolTip("导入扩展离线导出的岗位 JSON")
        self.btn_import.clicked.connect(self._on_import)
        self.header.add_action(self.btn_import)
        self.btn_refresh = ghost_button("刷新", "refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        self.header.add_action(self.btn_refresh)
        root.addWidget(self.header)
        root.addWidget(self._build_scan_card())

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_criteria_panel())
        self.splitter.addWidget(self._build_table_panel())
        self.splitter.addWidget(self._build_inspector_panel())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([286, 558, 310])
        root.addWidget(self.splitter, 1)

        self.shortcut_generate = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_generate.activated.connect(lambda: self._run("tailor", selected_only=True))
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self._focus_search)

    def _build_scan_card(self) -> Card:
        card = Card()
        card.setObjectName("scanCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 12, 10)
        row.setSpacing(14)

        bridge_box = QHBoxLayout()
        bridge_box.setSpacing(7)
        self.bridge_dot = QLabel("●")
        self.bridge_dot.setObjectName("warning")
        bridge_box.addWidget(self.bridge_dot)
        self.bridge_label = QLabel("浏览器桥接：未连接")
        self.bridge_label.setObjectName("warning")
        bridge_box.addWidget(self.bridge_label)
        row.addLayout(bridge_box)

        row.addWidget(self._vertical_rule())
        self.metric_total, self.metric_ready, self.metric_tailored = [], [], []
        for label, target in (
            ("已采集", self.metric_total),
            ("待评分", self.metric_ready),
            ("已生成", self.metric_tailored),
        ):
            value = QLabel("0")
            value.setObjectName("scanMetric")
            caption = QLabel(label)
            caption.setObjectName("scanMetricLabel")
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(value)
            box.addWidget(caption)
            row.addLayout(box)
            target.extend((value, caption))
        row.addStretch(1)

        self.btn_open_boss = secondary_button("打开 BOSS", "external")
        self.btn_open_boss.clicked.connect(self._on_open_boss)
        row.addWidget(self.btn_open_boss)
        self.btn_scan_start = QPushButton("启动遍历")
        self.btn_scan_start.setObjectName("primary")
        self.btn_scan_start.setIcon(themed_icon("play", 15))
        self.btn_scan_start.clicked.connect(self._on_start_scan)
        row.addWidget(self.btn_scan_start)
        self.btn_scan_pause = secondary_button("暂停", "pause")
        self.btn_scan_pause.clicked.connect(self._on_pause_scan)
        row.addWidget(self.btn_scan_pause)
        self.btn_scan_stop = ghost_button("停止", "stop")
        self.btn_scan_stop.setObjectName("danger")
        self.btn_scan_stop.clicked.connect(self._on_stop_scan)
        row.addWidget(self.btn_scan_stop)
        return card

    @staticmethod
    def _vertical_rule() -> QFrame:
        rule = QFrame()
        rule.setObjectName("divider")
        rule.setFixedWidth(1)
        rule.setFrameShape(QFrame.VLine)
        return rule

    def _build_criteria_panel_legacy(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(410)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(2, 2, 8, 8)
        layout.setSpacing(10)
        box = QGroupBox("求职意向与阈值")
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._criteria_widgets["directions"] = QPlainTextEdit()
        self._criteria_widgets["directions"].setFixedHeight(78)
        self._criteria_widgets["directions"].setPlaceholderText("每行一个，如：\n机器视觉\n视觉工程师\nAI 应用")
        form.addRow("目标方向：", self._criteria_widgets["directions"])

        self._criteria_widgets["cities"] = QPlainTextEdit()
        self._criteria_widgets["cities"].setFixedHeight(54)
        self._criteria_widgets["cities"].setPlaceholderText("每行一个，如：苏州\n上海")
        form.addRow("意向城市：", self._criteria_widgets["cities"])

        salary_row = QHBoxLayout()
        self._criteria_widgets["salary_min"] = NoWheelSpinBox()
        self._criteria_widgets["salary_min"].setRange(0, 500)
        self._criteria_widgets["salary_min"].setSuffix(" K")
        self._criteria_widgets["salary_min"].setFixedWidth(82)
        self._criteria_widgets["salary_max"] = NoWheelSpinBox()
        self._criteria_widgets["salary_max"].setRange(0, 500)
        self._criteria_widgets["salary_max"].setSuffix(" K")
        self._criteria_widgets["salary_max"].setFixedWidth(82)
        salary_row.addWidget(QLabel("下限"))
        salary_row.addWidget(self._criteria_widgets["salary_min"])
        salary_row.addWidget(QLabel("上限"))
        salary_row.addWidget(self._criteria_widgets["salary_max"])
        salary_row.addStretch(1)
        form.addRow("月度薪资：", salary_row)

        self._criteria_widgets["remote_ok"] = QCheckBox("接受远程 / 居家岗位")
        self._criteria_widgets["remote_ok"].setChecked(True)
        form.addRow("", self._criteria_widgets["remote_ok"])

        for key, label, height in (
            ("exclude_words", "排除词：", 58),
            ("exclude_companies", "排除公司：", 44),
        ):
            widget = QPlainTextEdit()
            widget.setFixedHeight(height)
            widget.setPlaceholderText("每行一个")
            self._criteria_widgets[key] = widget
            form.addRow(label, widget)

        self._criteria_widgets["experience"] = QLineEdit()
        self._criteria_widgets["experience"].setPlaceholderText("如：3-5 年；留空表示不限")
        form.addRow("经验要求：", self._criteria_widgets["experience"])
        self._criteria_widgets["education"] = QLineEdit()
        self._criteria_widgets["education"].setPlaceholderText("如：本科；留空表示不限")
        form.addRow("学历要求：", self._criteria_widgets["education"])

        for key, label, default, low, high in (
            ("recommend_threshold", "推荐阈值：", 78, 1, 100),
            ("review_threshold", "复核阈值：", 62, 0, 100),
            ("min_extension_score", "扩展分下限：", 0, 0, 100),
            ("max_tailor_per_run", "单次改写上限：", 5, 1, 50),
                ("scan_limit", "单方向扫描上限：", 30, 1, 500),
        ):
            spin = NoWheelSpinBox()
            spin.setRange(low, high)
            spin.setValue(default)
            self._criteria_widgets[key] = spin
            form.addRow(label, spin)

        layout.addWidget(box)

        strength_box = QGroupBox("生成时的表达强弱")
        strength_layout = QVBoxLayout(strength_box)
        strength_layout.setSpacing(7)
        self._criteria_widgets["rewrite_strength"] = QComboBox()
        for key in ("precise", "standard", "tactful"):
            self._criteria_widgets["rewrite_strength"].addItem(STRENGTH_LABELS[key], key)
        self._criteria_widgets["rewrite_strength"].setToolTip(
            "只改变措辞与侧重点，不增加任何事实、技能、数字或经历。"
        )
        strength_layout.addWidget(self._criteria_widgets["rewrite_strength"])
        examples = QLabel(
            "精准：把已有经历对准岗位关注点，措辞更贴合，但不照搬 JD。\n"
            "标准：专业、平衡，像一份自然定制的履历。\n"
            "委婉：用更通用的说法描述同一段真实经历，降低专门定制的痕迹。\n\n"
            "换档会被视为新的生成条件；已有结果只有在履历、岗位、意向与强弱"
            "全部一致时才会直接复用，审计过程不调用模型。"
        )
        examples.setObjectName("hint")
        examples.setWordWrap(True)
        strength_layout.addWidget(examples)
        layout.addWidget(strength_box)

        hint = QLabel(
            "桌面程序把意向条件下发给扩展；扩展遍历 BOSS 页面并实时回报岗位。"
            "本地硬门槛先排除明显不合适的岗位，再由 AI 按方向 40、职责 25、"
            "行业 15、薪资 10、职级/公司 10 评分。扩展分只作参考。\n\n"
            "推荐 ≥ 推荐阈值；复核 ≥ 复核阈值；其余淘汰。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        layout.addStretch(1)
        scroll.setWidget(holder)
        return scroll

    def _build_criteria_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("criteriaScroll")
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(270)
        scroll.setMaximumWidth(330)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("criteriaBody")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 3, 8)
        layout.setSpacing(10)

        intent_card = Card()
        intent_card.setObjectName("criteriaCard")
        box = QVBoxLayout(intent_card)
        box.setContentsMargins(13, 12, 13, 12)
        box.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("求职条件")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        local_chip = ChipLabel("本地保存", "neutral")
        head.addWidget(local_chip)
        box.addLayout(head)
        helper = QLabel("最多 3 个方向会作为扩展的搜索词；阈值仅决定状态，不会自动生成简历。")
        helper.setObjectName("fieldHelp")
        helper.setWordWrap(True)
        box.addWidget(helper)

        def add_field(label: str, widget: QWidget):
            field = QLabel(label)
            field.setObjectName("fieldLabel")
            box.addWidget(field)
            box.addWidget(widget)

        self._criteria_widgets["directions"] = QPlainTextEdit()
        self._criteria_widgets["directions"].setFixedHeight(66)
        self._criteria_widgets["directions"].setPlaceholderText("每行一个方向，如：机器视觉\n视觉工程师")
        add_field("目标方向", self._criteria_widgets["directions"])

        self._criteria_widgets["cities"] = QPlainTextEdit()
        self._criteria_widgets["cities"].setFixedHeight(48)
        self._criteria_widgets["cities"].setPlaceholderText("每行一个城市，如：苏州\n上海")
        add_field("意向城市", self._criteria_widgets["cities"])

        salary_label = QLabel("月度薪资（K）")
        salary_label.setObjectName("fieldLabel")
        box.addWidget(salary_label)
        salary_row = QHBoxLayout()
        salary_row.setSpacing(5)
        self._criteria_widgets["salary_min"] = NoWheelSpinBox()
        self._criteria_widgets["salary_min"].setRange(0, 500)
        self._criteria_widgets["salary_min"].setSuffix(" K")
        self._criteria_widgets["salary_min"].setFixedWidth(104)
        self._criteria_widgets["salary_max"] = NoWheelSpinBox()
        self._criteria_widgets["salary_max"].setRange(0, 500)
        self._criteria_widgets["salary_max"].setSuffix(" K")
        self._criteria_widgets["salary_max"].setFixedWidth(104)
        salary_row.addWidget(self._criteria_widgets["salary_min"], 1)
        dash = QLabel("—")
        dash.setObjectName("muted")
        salary_row.addWidget(dash)
        salary_row.addWidget(self._criteria_widgets["salary_max"], 1)
        box.addLayout(salary_row)

        self._criteria_widgets["remote_ok"] = QCheckBox("接受远程 / 居家岗位")
        self._criteria_widgets["remote_ok"].setChecked(True)
        box.addWidget(self._criteria_widgets["remote_ok"])

        for key, label, height in (
            ("exclude_words", "排除词", 44),
            ("exclude_companies", "排除公司", 40),
        ):
            widget = QPlainTextEdit()
            widget.setFixedHeight(height)
            widget.setPlaceholderText("每行一个")
            self._criteria_widgets[key] = widget
            add_field(label, widget)

        self._criteria_widgets["experience"] = QLineEdit()
        self._criteria_widgets["experience"].setPlaceholderText("如：3-5 年；留空表示不限")
        add_field("经验要求", self._criteria_widgets["experience"])
        self._criteria_widgets["education"] = QLineEdit()
        self._criteria_widgets["education"].setPlaceholderText("如：本科；留空表示不限")
        add_field("学历要求", self._criteria_widgets["education"])

        threshold_row = QHBoxLayout()
        threshold_row.setSpacing(7)
        for key, label, default, low, high in (
            ("recommend_threshold", "推荐 ≥", 78, 1, 100),
            ("review_threshold", "复核 ≥", 62, 0, 100),
        ):
            column = QVBoxLayout()
            column.setSpacing(3)
            text = QLabel(label)
            text.setObjectName("fieldLabel")
            column.addWidget(text)
            spin = NoWheelSpinBox()
            spin.setRange(low, high)
            spin.setValue(default)
            self._criteria_widgets[key] = spin
            column.addWidget(spin)
            threshold_row.addLayout(column, 1)
        box.addLayout(threshold_row)

        advanced_row = QGridLayout()
        advanced_row.setSpacing(7)
        for index, (key, label, default, low, high) in enumerate((
            ("scan_limit", "扫描上限", 30, 1, 500),
            ("min_extension_score", "扩展分", 0, 0, 100),
            ("max_tailor_per_run", "改写上限", 5, 1, 50),
        )):
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(3)
            text = QLabel(label)
            text.setObjectName("fieldLabel")
            column.addWidget(text)
            spin = NoWheelSpinBox()
            spin.setRange(low, high)
            spin.setValue(default)
            spin.setToolTip({
                "scan_limit": "每个目标方向最多采集的岗位数",
                "min_extension_score": "浏览器扩展给出的参考分下限",
                "max_tailor_per_run": "一次流水线最多生成多少份文字简历",
            }[key])
            self._criteria_widgets[key] = spin
            column.addWidget(spin)
            wrapper = QWidget()
            wrapper.setLayout(column)
            if index < 2:
                advanced_row.addWidget(wrapper, 0, index)
            else:
                spin.setMaximumWidth(140)
                advanced_row.addWidget(wrapper, 1, 0, 1, 2)
        box.addLayout(advanced_row)

        self.btn_save_criteria = secondary_button("保存条件", "save")
        self.btn_save_criteria.clicked.connect(lambda: self._save_criteria(show_message=True))
        box.addWidget(self.btn_save_criteria)
        layout.addWidget(intent_card)

        strength_card = Card()
        strength_card.setObjectName("criteriaCard")
        strength_layout = QVBoxLayout(strength_card)
        strength_layout.setContentsMargins(13, 12, 13, 12)
        strength_layout.setSpacing(7)
        strength_title = QLabel("表达强度")
        strength_title.setObjectName("sectionTitle")
        strength_layout.addWidget(strength_title)
        self._criteria_widgets["rewrite_strength"] = QComboBox()
        for key in ("precise", "standard", "tactful"):
            self._criteria_widgets["rewrite_strength"].addItem(STRENGTH_LABELS[key], key)
        self._criteria_widgets["rewrite_strength"].setToolTip(
            "只改变措辞与侧重点，不增加任何事实、技能、数字或经历。"
        )
        strength_layout.addWidget(self._criteria_widgets["rewrite_strength"])
        examples = QLabel(
            "精准：已有经历更贴近岗位关注点，但不照搬 JD。\n"
            "标准：专业、平衡，像一份自然定制的履历。\n"
            "委婉：用更通用的说法表达同一段真实经历，降低专用定制的痕迹。"
        )
        examples.setObjectName("fieldHelp")
        examples.setWordWrap(True)
        strength_layout.addWidget(examples)
        reuse = QLabel("换档会被视为新的生成条件；复用审计在本地完成，不调用模型。")
        reuse.setObjectName("fieldHelp")
        reuse.setWordWrap(True)
        strength_layout.addWidget(reuse)
        layout.addWidget(strength_card)

        score_hint = QLabel(
            "意向评分：方向 40 · 职责 25 · 行业 15 · 薪资/职级 20。"
            "本地门槛先排除明显不合适的岗位，扩展分只作参考。"
        )
        score_hint.setObjectName("fieldHelp")
        score_hint.setWordWrap(True)
        layout.addWidget(score_hint)
        layout.addStretch(1)
        scroll.setWidget(holder)
        return scroll

    def _build_table_panel_legacy(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        top = QHBoxLayout()
        self.summary = QLabel("岗位池为空")
        self.summary.setObjectName("sectionTitle")
        top.addWidget(self.summary, 1)
        self.btn_clear_current = QPushButton("清空当前列表")
        self.btn_clear_current.setObjectName("danger")
        self.btn_clear_current.setToolTip("只从当前列表隐藏，不删除岗位、评分或文字简历")
        self.btn_clear_current.clicked.connect(self._clear_current_list)
        top.addWidget(self.btn_clear_current)
        layout.addLayout(top)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索公司、岗位、城市…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill_table)
        controls.addWidget(self.search, 1)
        self.filter = QComboBox()
        for label, value in (
            ("全部", "all"), ("待评分", "unscored"), ("推荐", "recommended"),
            ("复核", "review"), ("淘汰", "rejected"), ("详情不足", "needs_detail"),
            ("评分失败", "error"), ("已改写", "tailored"),
        ):
            self.filter.addItem(label, value)
        self.filter.currentIndexChanged.connect(self._fill_table)
        controls.addWidget(self.filter)
        self.sort = QComboBox()
        for label, value in (
            ("最新采集", "recent"), ("意向分最高", "score"),
            ("薪资最高", "salary"), ("公司/岗位", "name"),
        ):
            self.sort.addItem(label, value)
        self.sort.currentIndexChanged.connect(self._fill_table)
        controls.addWidget(self.sort)
        self.show_hidden = QCheckBox("显示已隐藏")
        self.show_hidden.toggled.connect(self._toggle_hidden)
        controls.addWidget(self.show_hidden)
        self.btn_unhide = QPushButton("恢复已隐藏")
        self.btn_unhide.setObjectName("ghost")
        self.btn_unhide.clicked.connect(self._unhide_all)
        controls.addWidget(self.btn_unhide)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["选择", "状态", "意向分", "岗位", "公司", "城市", "薪资", "扩展分", "采集时间", "简历"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for col in range(4, 10):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._open_detail)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.setObjectName("ghost")
        btn_all.clicked.connect(lambda: self._check_all(True))
        actions.addWidget(btn_all)
        btn_none = QPushButton("清空选择")
        btn_none.setObjectName("ghost")
        btn_none.clicked.connect(lambda: self._check_all(False))
        actions.addWidget(btn_none)
        self.btn_score_all = QPushButton("评分全部")
        self.btn_score_all.setObjectName("secondary")
        self.btn_score_all.clicked.connect(lambda: self._run("score", selected_only=False))
        self.btn_score_selected = QPushButton("评分所选")
        self.btn_score_selected.setObjectName("secondary")
        self.btn_score_selected.clicked.connect(lambda: self._run("score", selected_only=True))
        self.btn_tailor = QPushButton("生成当前所选岗位简历")
        self.btn_tailor.setObjectName("primary")
        self.btn_tailor.setToolTip("对已勾选的任意状态岗位生成；生成前会本地审计是否可复用  Ctrl+Enter")
        self.btn_tailor.clicked.connect(lambda: self._run("tailor", selected_only=True))
        self.btn_pipeline = QPushButton("运行完整流水线")
        self.btn_pipeline.setObjectName("secondary")
        self.btn_pipeline.clicked.connect(lambda: self._run("all", selected_only=False))
        for btn in (self.btn_score_all, self.btn_score_selected, self.btn_tailor, self.btn_pipeline):
            actions.addWidget(btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        return panel

    def _build_table_panel(self) -> QWidget:
        card = Card()
        card.setObjectName("tableCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("tableToolbar")
        top = QHBoxLayout(toolbar)
        top.setContentsMargins(12, 9, 9, 8)
        top.setSpacing(7)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("岗位列表")
        title.setObjectName("tableTitle")
        title_box.addWidget(title)
        self.summary = QLabel("岗位池为空")
        self.summary.setObjectName("tableMeta")
        self.summary.setWordWrap(True)
        title_box.addWidget(self.summary)
        top.addLayout(title_box, 1)
        self.btn_clear_current = ghost_button("清空", "trash")
        self.btn_clear_current.setToolTip("只从当前列表隐藏，不删除岗位、评分或文字简历")
        self.btn_clear_current.clicked.connect(self._clear_current_list)
        top.addWidget(self.btn_clear_current)
        layout.addWidget(toolbar)

        controls = QWidget()
        control_stack = QVBoxLayout(controls)
        control_stack.setContentsMargins(9, 7, 9, 7)
        control_stack.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索公司、岗位、城市…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill_table)
        control_stack.addWidget(self.search)
        control_row = QHBoxLayout()
        control_row.setSpacing(6)
        self.filter = QComboBox()
        for label, value in (
            ("全部", "all"), ("待评分", "unscored"), ("推荐", "recommended"),
            ("复核", "review"), ("淘汰", "rejected"), ("详情不足", "needs_detail"),
            ("评分失败", "error"), ("已改写", "tailored"),
        ):
            self.filter.addItem(label, value)
        self.filter.setMaximumWidth(96)
        self.filter.currentIndexChanged.connect(self._fill_table)
        control_row.addWidget(self.filter, 1)
        self.sort = QComboBox()
        for label, value in (
            ("最新采集", "recent"), ("意向分最高", "score"),
            ("薪资最高", "salary"), ("公司/岗位", "name"),
        ):
            self.sort.addItem(label, value)
        self.sort.setMaximumWidth(126)
        self.sort.currentIndexChanged.connect(self._fill_table)
        control_row.addWidget(self.sort, 1)
        self.show_hidden = QCheckBox("隐藏")
        self.show_hidden.toggled.connect(self._toggle_hidden)
        control_row.addWidget(self.show_hidden)
        self.btn_unhide = ghost_button("", "refresh")
        self.btn_unhide.setFixedWidth(32)
        self.btn_unhide.setToolTip("恢复所有已隐藏岗位")
        self.btn_unhide.clicked.connect(self._unhide_all)
        control_row.addWidget(self.btn_unhide)
        control_stack.addLayout(control_row)
        layout.addWidget(controls)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("jobTable")
        self.table.setHorizontalHeaderLabels(
            ["", "状态", "匹配", "岗位信息", "简历", "采集"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 30)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 70)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 52)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 72)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 68)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.itemDoubleClicked.connect(self._open_detail)
        layout.addWidget(self.table, 1)

        bulk = QFrame()
        bulk.setObjectName("bulkbar")
        actions = QVBoxLayout(bulk)
        actions.setContentsMargins(9, 5, 9, 6)
        actions.setSpacing(4)
        first = QHBoxLayout()
        first.setSpacing(5)
        self.selection_meta = QLabel("未选择岗位")
        self.selection_meta.setObjectName("selectionMeta")
        first.addWidget(self.selection_meta)
        first.addStretch(1)
        btn_all = ghost_button("全选")
        btn_all.clicked.connect(lambda: self._check_all(True))
        first.addWidget(btn_all)
        btn_none = ghost_button("清空选择")
        btn_none.clicked.connect(lambda: self._check_all(False))
        first.addWidget(btn_none)
        actions.addLayout(first)
        second = QHBoxLayout()
        second.setSpacing(5)
        self.btn_score_all = secondary_button("评估全部")
        self.btn_score_all.clicked.connect(lambda: self._run("score", selected_only=False))
        second.addWidget(self.btn_score_all)
        self.btn_score_selected = secondary_button("评估所选")
        self.btn_score_selected.clicked.connect(lambda: self._run("score", selected_only=True))
        second.addWidget(self.btn_score_selected)
        self.btn_pipeline = secondary_button("完整流水线")
        self.btn_pipeline.clicked.connect(lambda: self._run("all", selected_only=False))
        second.addWidget(self.btn_pipeline)
        second.addStretch(1)
        actions.addLayout(second)
        self.btn_tailor = QPushButton("生成所选岗位简历")
        self.btn_tailor.setObjectName("primary")
        self.btn_tailor.setToolTip("对已勾选的任意状态岗位生成；生成前会本地审计是否可复用  Ctrl+Enter")
        self.btn_tailor.clicked.connect(lambda: self._run("tailor", selected_only=True))
        actions.addWidget(self.btn_tailor)
        layout.addWidget(bulk)
        return card

    def _build_inspector_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("inspector")
        card.setMinimumWidth(282)
        card.setMaximumWidth(346)
        root = QVBoxLayout(card)
        root.setContentsMargins(13, 12, 13, 12)
        root.setSpacing(8)
        eyebrow = QLabel("INSPECTOR")
        eyebrow.setObjectName("sectionKicker")
        root.addWidget(eyebrow)
        head = QHBoxLayout()
        head_title = QLabel("岗位详情")
        head_title.setObjectName("cardTitle")
        head.addWidget(head_title)
        head.addStretch(1)
        self.inspector_score_chip = ChipLabel("未评分", "neutral")
        head.addWidget(self.inspector_score_chip)
        root.addLayout(head)
        root.addWidget(Divider())

        scroll = QScrollArea()
        scroll.setObjectName("inspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        holder = QWidget()
        holder.setObjectName("inspectorHolder")
        holder.setAutoFillBackground(False)
        self.inspector_layout = QVBoxLayout(holder)
        self.inspector_layout.setContentsMargins(0, 0, 3, 0)
        self.inspector_layout.setSpacing(9)
        self.inspector_empty = QWidget()
        self.inspector_empty.setObjectName("inspectorEmpty")
        empty_layout = QVBoxLayout(self.inspector_empty)
        empty_layout.setContentsMargins(12, 28, 12, 12)
        empty_layout.setSpacing(5)
        empty_title = QLabel("选择一个岗位")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_body = QLabel("单击中间列表查看评分维度、推荐理由与岗位摘要。")
        empty_body.setObjectName("emptyBody")
        empty_body.setAlignment(Qt.AlignCenter)
        empty_body.setWordWrap(True)
        empty_layout.addWidget(empty_body)
        empty_layout.addStretch(1)
        self.inspector_layout.addWidget(self.inspector_empty)

        self.inspector_content = QWidget()
        self.inspector_content.setObjectName("inspectorContent")
        content = QVBoxLayout(self.inspector_content)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(8)
        self.inspector_title = QLabel("岗位名称")
        self.inspector_title.setObjectName("inspectorTitle")
        self.inspector_title.setWordWrap(True)
        content.addWidget(self.inspector_title)
        self.inspector_company = QLabel("")
        self.inspector_company.setObjectName("inspectorCompany")
        self.inspector_company.setWordWrap(True)
        content.addWidget(self.inspector_company)
        self.inspector_meta = QLabel("")
        self.inspector_meta.setObjectName("inspectorMeta")
        self.inspector_meta.setWordWrap(True)
        content.addWidget(self.inspector_meta)

        self.btn_generate_current = QPushButton("生成此岗位简历")
        self.btn_generate_current.setObjectName("primary")
        self.btn_generate_current.clicked.connect(self._generate_inspector_job)
        content.addWidget(self.btn_generate_current)
        self.btn_open_job = QPushButton("打开原岗位 ↗")
        self.btn_open_job.setObjectName("linkButton")
        self.btn_open_job.clicked.connect(self._open_inspector_url)
        content.addWidget(self.btn_open_job, 0, Qt.AlignLeft)
        content.addWidget(Divider())

        score_head = QHBoxLayout()
        score_title = QLabel("意向匹配")
        score_title.setObjectName("cardTitle")
        score_head.addWidget(score_title)
        score_head.addStretch(1)
        score_hint = QLabel("四维")
        score_hint.setObjectName("smallLabel")
        score_head.addWidget(score_hint)
        content.addLayout(score_head)
        for key, label, maximum in (
            ("direction", "方向", 40),
            ("responsibilities", "职责", 25),
            ("industry", "行业", 15),
            ("combined", "薪资 / 职级", 20),
        ):
            self._add_score_row(content, key, label, maximum)

        why_title = QLabel("为什么推荐")
        why_title.setObjectName("cardTitle")
        content.addWidget(why_title)
        self.inspector_reason = QLabel("尚未评分。")
        self.inspector_reason.setObjectName("inspectorBody")
        self.inspector_reason.setWordWrap(True)
        content.addWidget(self.inspector_reason)
        content.addWidget(Divider())

        resume_head = QHBoxLayout()
        resume_title = QLabel("简历状态")
        resume_title.setObjectName("cardTitle")
        resume_head.addWidget(resume_title)
        resume_head.addStretch(1)
        self.inspector_resume_chip = ChipLabel("未生成", "neutral")
        resume_head.addWidget(self.inspector_resume_chip)
        content.addLayout(resume_head)
        self.inspector_resume_meta = QLabel("尚未生成文字简历。")
        self.inspector_resume_meta.setObjectName("inspectorBody")
        self.inspector_resume_meta.setWordWrap(True)
        content.addWidget(self.inspector_resume_meta)
        self.btn_open_resume = QPushButton("在简历库中打开 →")
        self.btn_open_resume.setObjectName("linkButton")
        self.btn_open_resume.clicked.connect(self._open_inspector_resume)
        content.addWidget(self.btn_open_resume, 0, Qt.AlignLeft)

        content.addWidget(Divider())
        summary_title = QLabel("岗位摘要")
        summary_title.setObjectName("cardTitle")
        content.addWidget(summary_title)
        self.inspector_summary = QLabel("")
        self.inspector_summary.setObjectName("inspectorBody")
        self.inspector_summary.setWordWrap(True)
        content.addWidget(self.inspector_summary)
        self.btn_detail = QPushButton("查看完整 JD 与评分明细…")
        self.btn_detail.setObjectName("linkButton")
        self.btn_detail.clicked.connect(self._open_inspector_detail)
        content.addWidget(self.btn_detail, 0, Qt.AlignLeft)
        content.addStretch(1)
        self.inspector_layout.addWidget(self.inspector_content)
        scroll.setWidget(holder)
        self.inspector_layout.addStretch(1)
        self.inspector_content.hide()
        root.addWidget(scroll, 1)
        return card

    def _add_score_row(self, layout: QVBoxLayout, key: str, label: str, maximum: int):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 4, 0)
        name = QLabel(label)
        name.setObjectName("scoreRowLabel")
        row.addWidget(name, 1)
        value = QLabel("—")
        value.setObjectName("scoreRowValue")
        value.setMinimumWidth(44)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(value)
        layout.addLayout(row)
        bar = QProgressBar()
        bar.setObjectName("scoreBar")
        bar.setRange(0, maximum)
        bar.setValue(0)
        bar.setTextVisible(False)
        layout.addWidget(bar)
        self._score_rows[key] = (value, bar)

    # ------------------------------------------------------------ 数据
    def _load_criteria(self):
        criteria = intent.load_criteria()
        for key in ("directions", "cities", "exclude_words", "exclude_companies"):
            self._criteria_widgets[key].setPlainText("\n".join(criteria.get(key) or []))
        self._criteria_widgets["salary_min"].setValue(criteria.get("salary_min", 0))
        self._criteria_widgets["salary_max"].setValue(criteria.get("salary_max", 0))
        self._criteria_widgets["remote_ok"].setChecked(bool(criteria.get("remote_ok", True)))
        self._criteria_widgets["experience"].setText(criteria.get("experience") or "")
        self._criteria_widgets["education"].setText(criteria.get("education") or "")
        for key in ("recommend_threshold", "review_threshold", "min_extension_score",
                    "max_tailor_per_run", "scan_limit"):
            self._criteria_widgets[key].setValue(criteria.get(key) or 0)
        strength = intent.normalize_rewrite_strength(criteria.get("rewrite_strength"))
        index = self._criteria_widgets["rewrite_strength"].findData(strength)
        self._criteria_widgets["rewrite_strength"].setCurrentIndex(max(0, index))

    def read_criteria(self) -> dict:
        data = {
            "directions": intent.parse_list(self._criteria_widgets["directions"].toPlainText()),
            "cities": intent.parse_list(self._criteria_widgets["cities"].toPlainText()),
            "salary_min": self._criteria_widgets["salary_min"].value(),
            "salary_max": self._criteria_widgets["salary_max"].value(),
            "remote_ok": self._criteria_widgets["remote_ok"].isChecked(),
            "exclude_words": intent.parse_list(self._criteria_widgets["exclude_words"].toPlainText()),
            "exclude_companies": intent.parse_list(self._criteria_widgets["exclude_companies"].toPlainText()),
            "experience": self._criteria_widgets["experience"].text().strip(),
            "education": self._criteria_widgets["education"].text().strip(),
            "recommend_threshold": self._criteria_widgets["recommend_threshold"].value(),
            "review_threshold": self._criteria_widgets["review_threshold"].value(),
            "min_extension_score": self._criteria_widgets["min_extension_score"].value(),
            "max_tailor_per_run": self._criteria_widgets["max_tailor_per_run"].value(),
            "scan_limit": self._criteria_widgets["scan_limit"].value(),
            "rewrite_strength": self._criteria_widgets["rewrite_strength"].currentData(),
        }
        return intent.normalize_criteria(data)

    def _save_criteria(self, show_message: bool = False) -> dict:
        try:
            criteria = intent.save_criteria(self.read_criteria())
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            raise
        for key in ("recommend_threshold", "review_threshold"):
            self._criteria_widgets[key].setValue(criteria.get(key) or 0)
        if show_message:
            self.status.emit("意向设置已保存")
            QMessageBox.information(self, "已保存", "求职意向与评分阈值已保存。")
        return criteria

    def refresh(self):
        self.jobs = job_store.load_pool()
        self.hidden_ids = job_store.load_hidden()
        valid_ids = {job.get("id") for job in self.jobs if job.get("id")}
        self._selected_job_ids.intersection_update(valid_ids)
        counts = job_store.status_counts(self.jobs)
        visible_count = len([j for j in self.jobs if j.get("id") not in self.hidden_ids])
        self.summary.setText(
            "%d 个岗位 · 推荐 %d · 复核 %d · 已生成 %d"
            % (visible_count, counts["recommended"], counts["review"], counts["tailored"])
        )
        self.btn_unhide.setEnabled(bool(self.hidden_ids))
        self.metric_total[0].setText(str(visible_count))
        self.metric_ready[0].setText(str(counts["unscored"]))
        self.metric_tailored[0].setText(str(counts["tailored"]))
        self._fill_table()
        self._update_selection_count()

    @property
    def has_running_work(self) -> bool:
        return bool(
            self._busy or self._scan_running or self._live_worker is not None
            or self._bridge_jobs_queue or self.keeper.busy()
        )

    def reload_for_profile(self):
        """角色切换后重新读取当前角色的意向、隐藏列表和岗位池。"""
        self._selected_job_ids.clear()
        self._show_hidden = False
        if hasattr(self, "show_hidden"):
            self.show_hidden.setChecked(False)
        if hasattr(self, "search"):
            self.search.clear()
        self._load_criteria()
        self.refresh()

    def _visible_jobs(self) -> list:
        value = self.filter.currentData()
        if value == "tailored":
            jobs = [j for j in self.jobs if (j.get("tailored") or {}).get("text")]
        elif value in (None, "all"):
            jobs = list(self.jobs)
        else:
            jobs = [j for j in self.jobs if (j.get("intent") or {}).get("status", "unscored") == value]
        if not self._show_hidden:
            jobs = [j for j in jobs if j.get("id") not in self.hidden_ids]
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        if query:
            jobs = [
                j for j in jobs
                if query in "\n".join([
                    str(j.get("company") or ""), str(j.get("title") or ""),
                    str(j.get("city") or ""), str(j.get("salary") or ""),
                ]).lower()
            ]
        sort_key = self.sort.currentData() if hasattr(self, "sort") else "recent"
        if sort_key == "score":
            jobs.sort(key=lambda j: int((j.get("intent") or {}).get("score") or -1), reverse=True)
        elif sort_key == "salary":
            def salary_high(job):
                parsed = intent.parse_salary_range(job.get("salary") or "")
                return parsed[1] if parsed else -1
            jobs.sort(key=salary_high, reverse=True)
        elif sort_key == "name":
            jobs.sort(key=lambda j: ((j.get("company") or ""), (j.get("title") or "")))
        else:
            jobs.sort(
                key=lambda j: (j.get("scanned_at") or "", j.get("updated_at") or "",
                               j.get("imported_at") or ""),
                reverse=True,
            )
        return jobs

    def _fill_table(self):
        jobs = self._visible_jobs()
        selected_id = (self._inspector_job or {}).get("id")
        self._rows = []
        self._filling_table = True
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for job in jobs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(
                Qt.Checked if job.get("id") in self._selected_job_ids else Qt.Unchecked
            )
            check.setData(Qt.UserRole, job.get("id"))
            self.table.setItem(row, 0, check)
            intent_result = job.get("intent") or {}
            status = intent_result.get("status") or "unscored"
            self.table.setCellWidget(
                row, 1,
                self._chip_cell(self._table_status_label(status), self._status_variant(status)),
            )
            score = intent_result.get("score")
            self.table.setCellWidget(row, 2, self._score_cell(score))
            self.table.setItem(row, 3, QTableWidgetItem(""))
            self.table.item(row, 3).setData(Qt.UserRole, job.get("id"))
            self.table.item(row, 3).setToolTip(job.get("jd_text") or job_store.display_name(job))
            self.table.setCellWidget(row, 3, self._job_cell(job))
            tailored = job.get("tailored") or {}
            resume_text = "已生成" if tailored.get("text") else (
                "失败" if tailored.get("status") == "error" else "未生成"
            )
            resume_variant = "success" if tailored.get("text") else (
                "danger" if tailored.get("status") == "error" else "neutral"
            )
            self.table.setCellWidget(row, 4, self._chip_cell(resume_text, resume_variant))
            self.table.setCellWidget(
                row, 5,
                self._time_cell(job.get("scanned_at") or job.get("updated_at") or ""),
            )
            if job.get("id") in self.hidden_ids:
                self.table.item(row, 3).setToolTip("已隐藏，后台数据仍保留；可勾选后照常生成")
            self._rows.append(job)
        self.table.blockSignals(False)
        self._filling_table = False
        if selected_id:
            target = next((i for i, job in enumerate(self._rows) if job.get("id") == selected_id), -1)
            if target >= 0:
                self.table.selectRow(target)
                self._show_inspector(self._rows[target])
            else:
                self._clear_inspector()
        else:
            self._clear_inspector()
        self._update_selection_count()
        if not jobs:
            self.status.emit("当前筛选下没有岗位")

    @staticmethod
    def _status_variant(status: str) -> str:
        return {
            "recommended": "success", "review": "warning", "rejected": "danger",
            "needs_detail": "neutral", "error": "danger",
        }.get(status, "neutral")

    @staticmethod
    def _table_status_label(status: str) -> str:
        return {
            "needs_detail": "详情", "error": "失败",
        }.get(status, STATUS_LABELS.get(status, status))

    def _chip_cell(self, text: str, variant: str) -> QWidget:
        holder = QWidget()
        holder.setObjectName("jobCell")
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(holder)
        row.setContentsMargins(3, 0, 3, 0)
        row.setSpacing(0)
        chip = QLabel(text)
        chip.setObjectName("tableChip" + variant.capitalize())
        chip.setAlignment(Qt.AlignCenter)
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(chip, 0, Qt.AlignCenter)
        return holder

    def _score_cell(self, score) -> QWidget:
        holder = QWidget()
        holder.setObjectName("jobCell")
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(holder)
        row.setContentsMargins(3, 0, 3, 0)
        label = QLabel(str(score) if score is not None else "—")
        if score is None:
            label.setObjectName("scoreMuted")
        else:
            try:
                high = int(self._criteria_widgets["recommend_threshold"].value())
            except Exception:
                high = 78
            label.setObjectName("scoreHigh" if int(score) >= high else "scoreValue")
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        label.setAlignment(Qt.AlignCenter)
        row.addWidget(label, 1)
        return holder

    def _job_cell(self, job: dict) -> QWidget:
        holder = QWidget()
        holder.setObjectName("jobCell")
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(7, 3, 4, 3)
        layout.setSpacing(0)
        title = ElidedLabel(job.get("title") or "未命名岗位")
        title.setObjectName("jobTitle")
        title.setToolTip(job_store.display_name(job))
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(title)
        meta = [str(job.get("company") or "").strip()]
        meta.extend(
            str(job.get(key) or "").strip()
            for key in ("city", "salary")
            if str(job.get(key) or "").strip()
        )
        company = ElidedLabel(" · ".join(x for x in meta if x) or "公司未识别")
        company.setObjectName("jobCompany")
        company.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(company)
        return holder

    def _stacked_cell(self, upper: str, lower: str) -> QWidget:
        holder = QWidget()
        holder.setObjectName("jobCell")
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 3, 3, 3)
        layout.setSpacing(0)
        first = ElidedLabel(upper)
        first.setObjectName("jobSubValue")
        first.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(first)
        second = ElidedLabel(lower)
        second.setObjectName("jobCompany")
        second.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(second)
        return holder

    def _time_cell(self, value: str) -> QWidget:
        holder = QWidget()
        holder.setObjectName("jobCell")
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(3, 3, 2, 3)
        layout.setSpacing(0)
        first, second = self._compact_time(value)
        for text, name in ((first, "jobSubValue"), (second, "jobCompany")):
            label = QLabel(text)
            label.setObjectName(name)
            label.setAlignment(Qt.AlignCenter)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(label)
        holder.setToolTip(str(value or ""))
        return holder

    @staticmethod
    def _compact_time(value: str) -> tuple[str, str]:
        text = str(value or "").strip()
        if not text:
            return "—", ""
        try:
            stamp = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if len(text) >= 16:
                return stamp.strftime("%m-%d"), stamp.strftime("%H:%M")
            return stamp.strftime("%m-%d"), ""
        except (TypeError, ValueError):
            return text[:10], ""

    def _toggle_hidden(self, checked: bool):
        self._show_hidden = bool(checked)
        self._fill_table()

    def _unhide_all(self):
        if not self.hidden_ids:
            return
        answer = QMessageBox.question(
            self, "恢复已隐藏岗位",
            "将 %d 个已隐藏岗位重新显示在岗位池中？" % len(self.hidden_ids),
        )
        if answer != QMessageBox.Yes:
            return
        job_store.unhide_all()
        self._show_hidden = False
        self.show_hidden.setChecked(False)
        self.refresh()
        self.status.emit("已恢复隐藏岗位")

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "splitter"):
            return
        width = self.splitter.width()
        if width <= 0:
            return
        if width < 1100:
            left, right = 270, 282
        else:
            left, right = 286, 310
        center = max(360, width - left - right - 2 * self.splitter.handleWidth())
        self.splitter.setSizes([left, center, right])

    def _on_table_item_changed(self, item):
        if self._filling_table or item.column() != 0:
            return
        job_id = item.data(Qt.UserRole)
        if job_id:
            if item.checkState() == Qt.Checked:
                self._selected_job_ids.add(job_id)
            else:
                self._selected_job_ids.discard(job_id)
        self._update_selection_count()

    def _on_table_selection(self):
        if self._filling_table:
            return
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self._clear_inspector()
            return
        row = rows[0].row()
        if 0 <= row < len(self._rows):
            self._show_inspector(self._rows[row])

    def _selected_job(self) -> dict | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _show_inspector(self, job: dict):
        if not hasattr(self, "inspector_content"):
            return
        self._inspector_job = job
        self.inspector_empty.hide()
        self.inspector_content.show()
        self.inspector_title.setText(job.get("title") or "未命名岗位")
        self.inspector_company.setText(job.get("company") or "公司未识别")
        meta = [job.get("city"), job.get("salary"), job.get("experience"), job.get("education")]
        self.inspector_meta.setText(" · ".join(str(x) for x in meta if x) or "岗位元信息未识别")

        intent_result = job.get("intent") or {}
        status = intent_result.get("status") or "unscored"
        score = intent_result.get("score")
        self.inspector_score_chip.setText(
            "%s %s" % (STATUS_LABELS.get(status, status), score) if score is not None else "未评分"
        )
        self.inspector_score_chip.set_variant(self._status_variant(status))
        dims = intent_result.get("dimensions") or {}
        for key, raw_key, maximum in (
            ("direction", "direction", 40),
            ("responsibilities", "responsibilities", 25),
            ("industry", "industry", 15),
        ):
            self._set_inspector_score(key, dims.get(raw_key) or {}, maximum)
        salary_part = self._dimension_score(dims.get("salary") or {})
        level_part = self._dimension_score(dims.get("level_company") or {})
        combined = salary_part + level_part if (salary_part is not None or level_part is not None) else None
        self._set_inspector_score_value("combined", combined, 20)

        reason = str(intent_result.get("reason") or "").strip()
        if not reason:
            if score is None:
                reason = "尚未评分。勾选岗位后可在底部运行意向评估。"
            else:
                risks = intent_result.get("risks") or []
                reason = "；".join(str(x) for x in risks) if risks else "没有额外的推荐理由。"
        self.inspector_reason.setText(reason)

        tailored = job.get("tailored") or {}
        has_text = bool(tailored.get("text"))
        self.inspector_resume_chip.setText("已生成" if has_text else "未生成")
        self.inspector_resume_chip.set_variant("success" if has_text else "neutral")
        if has_text:
            self.inspector_resume_meta.setText(
                "生成于 %s · 校验提醒 %d 条\n正文可在简历库中整篇复制、修改和导出。"
                % (tailored.get("generated_at") or tailored.get("edited_at") or "-",
                   len(tailored.get("issues") or []))
            )
        else:
            self.inspector_resume_meta.setText("尚未生成文字简历。生成前会先做本地复用审计，不消耗接口额度。")
        self.btn_generate_current.setText("重新生成此岗位简历" if has_text else "生成此岗位简历")
        self.btn_open_resume.setVisible(has_text)
        self.btn_open_job.setEnabled(bool(str(job.get("url") or "").strip()))
        self.inspector_summary.setText(self._truncate_text(job.get("jd_text") or "没有完整 JD 正文。", 260))

    def _dimension_score(self, item: dict) -> int | None:
        try:
            value = item.get("score")
            return None if value is None else int(float(value))
        except (TypeError, ValueError):
            return None

    def _set_inspector_score(self, key: str, item: dict, maximum: int):
        self._set_inspector_score_value(key, self._dimension_score(item), maximum)

    def _set_inspector_score_value(self, key: str, score: int | None, maximum: int):
        pair = self._score_rows.get(key)
        if not pair:
            return
        value, bar = pair
        if score is None:
            value.setText("— / %d" % maximum)
            bar.setValue(0)
        else:
            value.setText("%d / %d" % (score, maximum))
            bar.setValue(max(0, min(maximum, score)))

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        clean = " ".join(str(text or "").split())
        return clean if len(clean) <= limit else clean[:limit].rstrip() + "…"

    def _clear_inspector(self):
        self._inspector_job = None
        if not hasattr(self, "inspector_content"):
            return
        self.inspector_content.hide()
        self.inspector_empty.show()
        self.inspector_score_chip.setText("未评分")
        self.inspector_score_chip.set_variant("neutral")

    def _update_selection_count(self):
        if not hasattr(self, "selection_meta"):
            return
        count = len(self._selected_job_ids)
        visible_count = sum(1 for job in self._rows if job.get("id") in self._selected_job_ids)
        if not count:
            text = "未选择岗位"
        elif visible_count < count:
            text = "已选择 %d 个岗位 · %d 个在当前筛选外" % (count, count - visible_count)
        else:
            text = "已选择 %d 个岗位" % count
        self.selection_meta.setText(text)
        enabled = count > 0 and not self._busy
        self.btn_score_selected.setEnabled(enabled)
        self.btn_tailor.setEnabled(enabled)

    def _generate_inspector_job(self):
        job = self._inspector_job
        if not job:
            return
        row = next((i for i, item in enumerate(self._rows) if item.get("id") == job.get("id")), -1)
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item:
            item.setCheckState(Qt.Checked)
        self.table.selectRow(row)
        self._run("tailor", selected_only=True)

    def _open_inspector_url(self):
        job = self._inspector_job or {}
        url = str(job.get("url") or "").strip()
        if not url:
            return
        ok, detail = browser.open_external_url(url)
        if not ok:
            QMessageBox.warning(self, "打开失败", "无法使用已选浏览器打开岗位链接：\n%s" % detail)
        else:
            self.status.emit("已用 %s 打开原岗位" % detail)

    def _open_inspector_resume(self):
        job = self._inspector_job or {}
        if job.get("id"):
            self.open_output_requested.emit(job["id"])

    def _open_inspector_detail(self):
        job = self._inspector_job
        if job:
            JobDetailDialog(job, self).exec_()

    def _clear_current_list(self):
        jobs = self._visible_jobs()
        ids = [job.get("id") for job in jobs if job.get("id") not in self.hidden_ids]
        if not ids:
            QMessageBox.information(self, "没有可清空的岗位", "当前筛选结果为空，或已经全部隐藏。")
            return
        answer = QMessageBox.question(
            self, "清空当前列表",
            "从当前列表中隐藏 %d 个岗位？\n\n"
            "岗位 JSON、SQLite 记录、评分和文字简历都会保留，可随时恢复显示。" % len(ids),
        )
        if answer != QMessageBox.Yes:
            return
        job_store.hide_jobs(ids)
        self._selected_job_ids.difference_update(ids)
        self.refresh()
        self.status.emit("已从当前列表隐藏 %d 个岗位，后台数据未删除" % len(ids))

    # ------------------------------------------------------------ 浏览器桥接
    def _on_bridge_connection(self, connected: bool, text: str = ""):
        self.bridge_dot.setObjectName("success" if connected else "warning")
        self.bridge_dot.style().unpolish(self.bridge_dot)
        self.bridge_dot.style().polish(self.bridge_dot)
        self.bridge_label.setObjectName("success" if connected else "warning")
        self.bridge_label.style().unpolish(self.bridge_label)
        self.bridge_label.style().polish(self.bridge_label)
        if connected:
            suffix = "（端口 %d）" % self.bridge.port if self.bridge and self.bridge.port else ""
            self.bridge_label.setText("浏览器桥接：已连接%s" % suffix)
            self.bridge_label.setToolTip(text or "采集扩展已连接")
        else:
            self.bridge_label.setText("浏览器桥接：未连接")
            self.bridge_label.setToolTip("请确认 Edge 已安装并启用采集扩展，且打开了 BOSS 直聘页面")
        self._update_scan_controls()

    def _on_bridge_failed(self, message: str):
        self.bridge_label.setText("浏览器桥接：启动失败")
        self.bridge_label.setObjectName("dangerText")
        self.bridge_label.style().unpolish(self.bridge_label)
        self.bridge_label.style().polish(self.bridge_label)
        self.bridge_label.setToolTip(str(message))
        self.status.emit("本地桥接失败：%s" % message)

    def _update_scan_controls(self):
        connected = bool(self.bridge and self.bridge.connected)
        self.btn_scan_start.setEnabled(connected and not self._scan_running and not self._busy)
        self.btn_scan_pause.setEnabled(connected and self._scan_running)
        self.btn_scan_stop.setEnabled(connected and self._scan_running)

    def _on_open_boss(self):
        try:
            criteria = self._save_criteria()
        except Exception:
            return
        direction = (criteria.get("directions") or [""])[0]
        if not direction:
            QMessageBox.warning(self, "缺少目标方向", "请先在左侧填写至少一个目标方向，再打开 BOSS。")
            return
        url = browser.last_boss_url() or ("https://www.zhipin.com/web/geek/jobs?query=" + quote(direction))
        ok, detail = browser.open_external_url(url)
        if not ok:
            QMessageBox.warning(self, "打开失败", "无法使用已选浏览器打开 BOSS：\n%s" % detail)
            return
        browser.remember_boss_url(url)
        self.status.emit("已用 %s 打开 BOSS，等待采集扩展连接" % detail)

    def _on_start_scan(self):
        if self._busy or self._scan_running:
            return
        if not self.bridge or not self.bridge.connected:
            QMessageBox.warning(
                self, "采集扩展未连接",
                "没有检测到浏览器采集扩展。\n\n"
                "请在 Edge 的 edge://extensions/ 中确认 BOSS-Auto-Job-Extension 已启用，"
                "然后刷新 BOSS 直聘页面。连接成功后这里会显示绿色状态。",
            )
            return
        try:
            criteria = self._save_criteria()
        except Exception:
            return
        if not criteria.get("directions"):
            QMessageBox.warning(self, "缺少目标方向", "浏览器遍历至少需要一个目标方向，作为 BOSS 搜索词。")
            return
        profile = self.profile_provider() if self.profile_provider else profile_text.load_profile_text().get("text", "")
        auto_tailor = False
        llm = self.ctx.llm()
        if not llm.api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在「设置」里填写 API Key，再启动岗位评分。")
            return

        scan_id = "scan-%s" % _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._scan_id = scan_id
        self._scan_criteria = criteria
        self._scan_profile = profile
        self._scan_auto_tailor = auto_tailor
        self._scan_expected = max(1, len(criteria["directions"]) * int(criteria["scan_limit"]))
        self._scan_seen = self._scan_processed = 0
        self._scan_recommended = self._scan_tailored = 0
        self._scan_failures = []
        self._scan_pending_finish = None
        self._scan_finalized = False
        self._bridge_jobs_queue = []
        try:
            job_db.record_scan_start(scan_id, criteria)
        except Exception as exc:
            self.status.emit("扫描记录写入失败，将继续执行：%s" % exc)
        command = {
            "type": "start_scan",
            "scan_id": scan_id,
            "criteria": {
                "directions": criteria.get("directions") or [],
                "cities": criteria.get("cities") or [],
                "salary_min": criteria.get("salary_min") or 0,
                "salary_max": criteria.get("salary_max") or 0,
                "exclude_words": criteria.get("exclude_words") or [],
                "exclude_companies": criteria.get("exclude_companies") or [],
                "scan_limit": criteria.get("scan_limit") or 30,
                "recommend_threshold": criteria.get("recommend_threshold") or 78,
                "review_threshold": criteria.get("review_threshold") or 62,
                "max_tailor_per_run": criteria.get("max_tailor_per_run") or 5,
            },
            "auto_tailor": auto_tailor,
        }
        if not self.bridge.send_command(command):
            self._scan_finalized = True
            try:
                job_db.record_scan_finish(scan_id, "failed", {"error": "bridge_send_failed"})
            except Exception:
                pass
            return
        self._scan_running = True
        self._update_scan_controls()
        self.progress.emit(1, "已下发遍历任务，等待扩展打开搜索页")
        self.status.emit("岗位遍历已启动：%s" % "、".join(criteria["directions"]))

    def _on_pause_scan(self):
        if not self._scan_running:
            return
        self.bridge.send_command({"type": "pause_scan", "scan_id": self._scan_id})
        self.status.emit("已下发暂停指令，当前岗位处理完后暂停")

    def _on_stop_scan(self):
        if not self._scan_running:
            return
        self.bridge.send_command({"type": "stop_scan", "scan_id": self._scan_id})
        self._scan_running = False
        if self._scan_pending_finish is None:
            self._scan_pending_finish = {"type": "scan_stopped", "message": "用户停止遍历"}
        self._update_scan_controls()
        self._finalize_scan_if_idle()
        self.status.emit("已下发停止指令；已回传的岗位仍会完成评分与入库")

    def _on_bridge_event(self, event: dict):
        kind = str(event.get("type") or "")
        scan_id = str(event.get("scan_id") or "")
        if scan_id and self._scan_id and scan_id != self._scan_id:
            return
        if kind == "hello":
            self._on_bridge_connection(True, event.get("page_title") or event.get("title") or "")
            return
        if kind == "scan_started":
            self._scan_running = True
            self._update_scan_controls()
            self.status.emit("扩展已开始遍历搜索词")
            return
        if kind == "scan_progress":
            message = str(event.get("message") or "正在遍历岗位")
            self.status.emit(message)
            return
        if kind == "scan_paused":
            self._scan_running = False
            try:
                job_db.record_scan_finish(self._scan_id, "paused", {
                    "seen": self._scan_seen,
                    "processed": self._scan_processed,
                    "extension": event,
                })
            except Exception as exc:
                self.status.emit("暂停状态写入失败：%s" % exc)
            self._update_scan_controls()
            self.status.emit("岗位遍历已暂停")
            return
        if kind in ("job", "record"):
            payload = event.get("job") if isinstance(event.get("job"), dict) else event.get("record")
            if not isinstance(payload, dict):
                payload = event
            self._scan_seen += 1
            self._bridge_jobs_queue.append(payload)
            self.status.emit("收到岗位 %d：%s" % (self._scan_seen, payload.get("title") or "未命名岗位"))
            self._start_next_live_job()
            return
        if kind == "scan_finished":
            self._scan_running = False
            self._scan_pending_finish = event
            self._update_scan_controls()
            self._finalize_scan_if_idle()
            return
        if kind == "scan_error":
            self._scan_running = False
            self._scan_pending_finish = event
            self._scan_failures.append({"stage": "scan", "job": "", "error": event.get("message") or "扫描失败"})
            self._update_scan_controls()
            self._finalize_scan_if_idle()
            return

    def _start_next_live_job(self):
        if self._live_worker is not None or not self._bridge_jobs_queue:
            self._finalize_scan_if_idle()
            return
        payload = self._bridge_jobs_queue.pop(0)
        self._live_job = payload
        criteria = self._scan_criteria or self._save_criteria()
        profile = self._scan_profile
        auto_tailor = self._scan_auto_tailor
        llm = self.ctx.llm()
        self.status.emit("正在处理岗位：%s" % (payload.get("title") or "未命名岗位"))
        worker = Worker(lambda cb: live.process_live_job(
            payload, criteria, profile, llm, auto_tailor=auto_tailor,
        ))
        self._live_worker = worker
        worker.done.connect(self._on_live_done)
        worker.failed.connect(self._on_live_failed)
        worker.finished.connect(self._on_live_finished)
        self.keeper.start(worker)

    def _on_live_done(self, result: dict):
        self._scan_processed += 1
        if result.get("status") == "recommended":
            self._scan_recommended += 1
        if result.get("tailored"):
            self._scan_tailored += 1
        if result.get("score_error"):
            self._scan_failures.append({"stage": "score", "job": result.get("title"), "error": result["score_error"]})
        if result.get("tailor_error"):
            self._scan_failures.append({"stage": "tailor", "job": result.get("title"), "error": result["tailor_error"]})
        percent = min(95, int(2 + 93 * self._scan_processed / max(1, self._scan_expected)))
        detail = "%s 分" % result.get("score") if result.get("score") is not None else "评分失败"
        extra = "，已生成文字简历" if result.get("tailored") else ""
        self.progress.emit(percent, "已处理 %d 个岗位：%s｜%s%s" % (
            self._scan_processed, result.get("title") or "未命名岗位", detail, extra
        ))
        self.jobs = job_store.load_pool()
        self._fill_table()

    def _on_live_failed(self, message: str):
        job = self._live_job or {}
        self._scan_failures.append({"stage": "live", "job": job.get("title"), "error": message})
        self._scan_processed += 1
        self.status.emit("实时岗位处理失败，继续后续岗位：%s" % message)

    def _on_live_finished(self):
        self._live_worker = None
        self._live_job = None
        if self._bridge_jobs_queue:
            self._start_next_live_job()
        else:
            self._finalize_scan_if_idle()

    def _finalize_scan_if_idle(self):
        if self._scan_finalized or self._scan_running or self._live_worker is not None or self._bridge_jobs_queue:
            return
        if self._scan_pending_finish is None:
            return
        self._scan_finalized = True
        payload = self._scan_pending_finish
        status = "failed" if payload.get("type") == "scan_error" else "finished"
        report = {
            "seen": self._scan_seen,
            "processed": self._scan_processed,
            "recommended": self._scan_recommended,
            "tailored": self._scan_tailored,
            "failures": self._scan_failures,
            "extension": payload,
        }
        try:
            job_db.record_scan_finish(self._scan_id, status, report)
        except Exception as exc:
            self.status.emit("扫描结束记录写入失败：%s" % exc)
        self.refresh()
        self.progress.emit(100, "岗位遍历结束：收到 %d，推荐 %d，生成 %d" % (
            self._scan_seen, self._scan_recommended, self._scan_tailored
        ))
        box = QMessageBox(self)
        box.setWindowTitle("岗位遍历结束" if status == "finished" else "岗位遍历中断")
        box.setText("收到岗位 %d 个｜评分 %d 个｜推荐 %d 个｜生成文字简历 %d 个\n失败 %d 个" % (
            self._scan_seen, self._scan_processed, self._scan_recommended,
            self._scan_tailored, len(self._scan_failures),
        ))
        if self._scan_failures:
            box.setDetailedText("\n".join(
                "[%s] %s：%s" % (f.get("stage"), f.get("job") or "", f.get("error"))
                for f in self._scan_failures
            ))
            box.setIcon(QMessageBox.Warning)
        else:
            box.setIcon(QMessageBox.Information)
        box.exec_()
        self.status.emit("岗位遍历结束：收到 %d，推荐 %d" % (self._scan_seen, self._scan_recommended))
        self._scan_pending_finish = None

    def _check_all(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        visible_ids = []
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item:
                    item.setCheckState(state)
                    job_id = item.data(Qt.UserRole)
                    if checked and job_id:
                        visible_ids.append(job_id)
        finally:
            self.table.blockSignals(False)
        if checked:
            self._selected_job_ids.update(visible_ids)
        else:
            self._selected_job_ids.clear()
        self._update_selection_count()

    def _selected_ids(self) -> list:
        ids, seen = [], set()
        for job in list(self._rows) + list(self.jobs):
            job_id = job.get("id")
            if job_id in self._selected_job_ids and job_id not in seen:
                ids.append(job_id)
                seen.add(job_id)
        return ids

    def _open_detail(self, item):
        row = item.row()
        if 0 <= row < len(self._rows):
            JobDetailDialog(self._rows[row], self).exec_()

    # ------------------------------------------------------------ 导入 / 运行
    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择扩展导出的 JSON", str(job_store.JOB_POOL_PATH.parent), "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            report = job_store.import_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            self.status.emit("岗位 JSON 导入失败")
            return
        self.refresh()
        text = (
            "新增 %d｜更新 %d｜无变化 %d｜无效 %d\n"
            "其中 JD 变化 %d｜JD 过短 %d｜岗位池共 %d 条"
            % (report["added"], report["updated"], report["unchanged"], report["invalid"],
               report["jd_changed"], report["short_jd"], report["pool_total"])
        )
        box = QMessageBox(self)
        box.setWindowTitle("导入完成")
        box.setText(text)
        if report["short_jd"]:
            box.setInformativeText(
                "有 %d 条岗位的 JD 正文不足 %d 字，可能是旧版导出记录。"
                "请用新版扩展重新采集后再导入。"
                % (report["short_jd"], job_store.MIN_USABLE_JD_CHARS)
            )
        box.exec_()
        self.status.emit("岗位池导入完成：新增 %d，更新 %d" % (report["added"], report["updated"]))

    def _set_busy(self, busy: bool):
        self._busy = busy
        for btn in (
            self.btn_import, self.btn_refresh, self.btn_save_criteria,
            self.btn_score_all, self.btn_score_selected, self.btn_tailor, self.btn_pipeline,
            self.btn_clear_current, self.btn_open_boss, self.btn_generate_current,
        ):
            btn.setEnabled(not busy)
        self._update_selection_count()
        self._update_scan_controls()

    def _run(self, mode: str, selected_only: bool):
        if self._busy:
            return
        if self._scan_running or self._live_worker is not None or self._bridge_jobs_queue:
            QMessageBox.warning(self, "遍历进行中", "浏览器岗位遍历尚未结束，请等待当前岗位处理完成后再运行批量流水线。")
            return
        try:
            criteria = self._save_criteria()
        except Exception:
            return
        selected = self._selected_ids()
        if selected_only and not selected:
            QMessageBox.warning(self, "没有选择", "请先勾选要处理的岗位。")
            return
        if not self.jobs:
            QMessageBox.warning(self, "岗位池为空", "请先导入扩展导出的 JSON。")
            return
        if mode in ("score", "all") and not (
            criteria["directions"] or criteria["cities"] or criteria["salary_min"]
        ):
            QMessageBox.warning(self, "意向未填写", "请至少填写目标方向、意向城市或薪资下限。")
            return
        profile = self.profile_provider() if self.profile_provider else profile_text.load_profile_text().get("text", "")

        force_tailor = False
        if mode == "tailor":
            wanted = set(selected)
            chosen_jobs = [job for job in self.jobs if job.get("id") in wanted]
            preflight = tailor_text.preflight_jobs(chosen_jobs, profile, criteria)
            plan = self._choose_tailor_plan(preflight)
            if plan == "open":
                self.outputs_ready.emit()
                return
            if not plan:
                return
            force_tailor = plan == "all"
            if len(profile.strip()) < 80:
                QMessageBox.warning(self, "履历太短", "请先在「我的履历」里补充完整的个人履历。")
                return
            llm = self.ctx.llm()
            if not llm.api_key:
                QMessageBox.warning(self, "缺少 API Key", "请先在「接口设置」里填写 API Key。")
                return
            self._set_busy(True)
            self.status.emit("正在按所选岗位生成文字简历…")
            worker = Worker(lambda cb: pipeline.run_batch(
                criteria, profile, llm, progress=cb, mode="tailor",
                selected_ids=selected, force_tailor=force_tailor,
            ))
            worker.progress.connect(self.progress)
            worker.done.connect(self._on_done)
            worker.failed.connect(self._on_failed)
            worker.finished.connect(lambda: self._set_busy(False))
            self.keeper.start(worker)
            return

        target_count = len(selected) if selected_only else len(self.jobs)
        if mode in ("score", "all") and target_count > 20:
            answer = QMessageBox.question(
                self, "确认批量评分",
                "本次最多需要调用 AI 评分 %d 个岗位，可能耗时并产生接口费用。\n\n是否继续？"
                % target_count,
            )
            if answer != QMessageBox.Yes:
                return
        if mode in ("tailor", "all") and len(profile.strip()) < 80:
            QMessageBox.warning(self, "履历太短", "请先在「我的履历」里补充完整的个人履历。")
            return
        llm = self.ctx.llm()
        if not llm.api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在「接口设置」里填写 API Key。")
            return

        self._set_busy(True)
        self.status.emit("正在运行岗位流水线…")
        worker = Worker(lambda cb: pipeline.run_batch(
            criteria, profile, llm, progress=cb, mode=mode,
            selected_ids=selected if selected_only else None,
        ))
        worker.progress.connect(self.progress)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._set_busy(False))
        self.keeper.start(worker)

    def _choose_tailor_plan(self, preflight: dict) -> str:
        """本地审计后让用户决定复用、补生成或全部重做；此步不联网。"""
        reusable = len(preflight.get("reusable") or [])
        stale = len(preflight.get("stale") or [])
        missing = len(preflight.get("missing") or [])
        required = stale + missing
        box = QMessageBox(self)
        box.setWindowTitle("生成前审计")
        box.setText(
            "所选 %d 个岗位：可复用 %d｜旧结果待更新 %d｜未生成 %d\n\n"
            "本地审计没有调用模型。可复用结果只有在岗位、JD、履历、意向和表达强弱"
            "全部一致时才会命中。" % (preflight.get("total", 0), reusable, stale, missing)
        )
        if required == 0:
            box.setInformativeText("已有可直接使用的当前版本，无需消耗接口额度。")
            open_btn = box.addButton("打开文字简历", QMessageBox.AcceptRole)
            regen_btn = box.addButton("仍要全部重新生成", QMessageBox.DestructiveRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.exec_()
            clicked = box.clickedButton()
            if clicked is open_btn:
                return "open"
            if clicked is regen_btn:
                return "all"
            return ""
        box.setInformativeText(
            "建议只生成缺失或已过期的 %d 份；选择全部重做会再生成 %d 份。"
            % (required, reusable)
        )
        missing_btn = box.addButton("仅生成缺失 / 过期", QMessageBox.AcceptRole)
        regen_btn = box.addButton("全部重新生成", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is missing_btn:
            return "missing"
        if clicked is regen_btn:
            return "all"
        return ""

    def _on_done(self, report: dict):
        self.refresh()
        text = (
            "意向评分 %d 条：推荐 %d，复核 %d，淘汰 %d，详情不足 %d\n"
            "文字改写成功 %d 条，复用当前版本 %d 条，更新旧结果 %d 条\n"
            "失败 %d 条"
            % (report.get("scored", 0), report.get("recommended", 0),
               report.get("review", 0), report.get("rejected", 0),
               report.get("needs_detail", 0), report.get("tailored", 0),
               report.get("reused_tailor", 0), report.get("stale_tailor", 0),
               len(report.get("failures") or []))
        )
        box = QMessageBox(self)
        box.setWindowTitle("流水线完成")
        box.setText(text)
        if report.get("failures"):
            details = "\n".join(
                "[%s] %s：%s" % (f.get("stage"), f.get("job"), f.get("error"))
                for f in report["failures"]
            )
            box.setDetailedText(details)
            box.setIcon(QMessageBox.Warning)
        else:
            box.setIcon(QMessageBox.Information)
        box.exec_()
        self.status.emit("流水线完成：改写 %d 条" % report.get("tailored", 0))
        if report.get("tailored") or report.get("reused_tailor"):
            self.outputs_ready.emit()

    def _on_failed(self, message: str):
        QMessageBox.critical(self, "流水线失败", message)
        self.status.emit("岗位流水线失败")
