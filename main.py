# -*- coding: utf-8 -*-
"""自适应简历生成器 V2 —— 程序入口。

界面：左侧工作区导航 + 个人履历 / 岗位工作台 / 简历库 / 设置四个页面。
所有耗时操作（调用大模型）都在后台线程执行，界面不会卡死；结束一律弹窗告知结果。
"""
from __future__ import annotations

import logging
import os
import sys
import traceback

from PyQt5.QtCore import QProcess, QSettings, QSize, Qt
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QButtonGroup, QDockWidget, QFrame,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from core import profiles
from core.applog import get_logger, setup_logging, shutdown_logging
from core.config import APP_DIR, DATA_DIR, LOG_DIR, load_config, save_config
from core.data_reset import clear_local_data
from ui.context import AppContext
from ui.bridge_service import BridgeService
from ui.components import ElidedLabel
from ui.data_reset_dialog import ClearDataDialog
from ui.icons import themed_icon
from ui.motion import fade_in
from ui.page_jobs import JobPoolPage
from ui.page_outputs import OutputsPage
from ui.page_profile import ProfilePage
from ui.page_settings import SettingsPage
from ui.profile_dialogs import RoleDialog
from ui.styles import apply_theme
from ui.widgets import LogEmitter, LogPanel, QtLogHandler

log = get_logger("main")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        profiles.apply_active_profile()
        self._skip_close_save = False
        self.setWindowTitle("自适应简历生成器 V2")
        self.resize(1360, 900)
        self.setMinimumSize(1240, 700)
        self.ctx = AppContext()
        self.bridge = BridgeService(self)
        self.bridge.failed.connect(self._on_bridge_failed)
        self.bridge.start()
        self._build_menu()
        self._build_central()
        self._build_log_dock()
        self._install_excepthook()
        self._update_role_chip()
        self._restore_window_state()
        log.info("程序启动，工作目录：%s", APP_DIR)

    # ------------------------------------------------------------ 菜单
    def _build_menu(self):
        bar = self.menuBar()

        m_file = bar.addMenu("文件(&F)")
        act_settings = QAction("接口设置…", self)
        act_settings.triggered.connect(self._open_settings)
        m_file.addAction(act_settings)
        m_file.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_role = bar.addMenu("角色(&R)")
        act_switch = QAction("切换 / 管理角色…", self)
        act_switch.setShortcut("Ctrl+Shift+R")
        act_switch.setToolTip("切换、创建或删除角色工作区")
        act_switch.triggered.connect(self._switch_role)
        m_role.addAction(act_switch)
        act_new = QAction("新建 / 导入角色…", self)
        act_new.triggered.connect(self._new_role)
        m_role.addAction(act_new)
        m_role.addSeparator()
        act_logout = QAction("退出当前角色", self)
        act_logout.triggered.connect(self._logout_role)
        m_role.addAction(act_logout)

        m_view = bar.addMenu("视图(&V)")
        theme_menu = m_view.addMenu("主题")
        cfg_theme = str((load_config().get("ui") or {}).get("theme") or "system")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        for label, mode in (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(mode)
            action.setChecked(mode == cfg_theme)
            action.triggered.connect(lambda _checked, m=mode: self._set_theme(m))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)

        m_tool = bar.addMenu("工具(&T)")
        for text, getter in (
            ("打开当前角色文件夹", self._current_role_dir),
            ("打开岗位池文件夹", self._current_jobs_dir),
            ("打开个人履历数据文件", self._current_profile_file),
            ("打开日志文件夹", lambda: LOG_DIR),
        ):
            act = QAction(text, self)
            act.triggered.connect(lambda _=False, get=getter: self._open_path(get()))
            m_tool.addAction(act)
        m_tool.addSeparator()
        act_log = QAction("显示 / 隐藏日志面板", self)
        act_log.triggered.connect(lambda: self.log_dock.setVisible(not self.log_dock.isVisible()))
        m_tool.addAction(act_log)

        m_help = bar.addMenu("帮助(&H)")
        act_help = QAction("使用说明", self)
        act_help.triggered.connect(lambda: self._open_path(APP_DIR / "使用说明.md"))
        m_help.addAction(act_help)
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

    # ------------------------------------------------------------ 主体
    def _build_central(self):
        central = QWidget()
        central.setObjectName("appRoot")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        workspace = QWidget()
        page_layout = QVBoxLayout(workspace)
        page_layout.setContentsMargins(22, 18, 22, 10)
        page_layout.setSpacing(10)

        self.stack = QStackedWidget()
        self.page_profile = ProfilePage(self.ctx)
        self.page_profile.role_requested.connect(self._switch_role)
        self.page_jobs = JobPoolPage(
            self.ctx,
            profile_provider=lambda: self.page_profile.current_text,
            bridge=self.bridge,
        )
        self.page_outputs = OutputsPage(self.ctx)
        self.page_settings = SettingsPage(self.ctx)
        for page in (self.page_profile, self.page_jobs, self.page_outputs, self.page_settings):
            self.stack.addWidget(page)
        page_layout.addWidget(self.stack, 1)

        footer = QFrame()
        footer.setObjectName("appFooter")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(10, 5, 8, 5)
        bottom.setSpacing(12)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("footerStatus")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(180)
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.progress)
        local_note = QLabel("本地优先 · 数据仅存本机")
        local_note.setObjectName("footerMeta")
        bottom.addWidget(local_note)
        page_layout.addWidget(footer)
        layout.addWidget(workspace, 1)
        self.setCentralWidget(central)

        self.bridge.connection_changed.connect(self._on_bridge_connection)
        self.page_jobs.progress.connect(self._on_progress)
        self.page_profile.status.connect(self._on_status)
        self.page_jobs.status.connect(self._on_status)
        self.page_outputs.status.connect(self._on_status)
        self.page_settings.status.connect(self._on_status)
        self.page_settings.theme_changed.connect(self._set_theme)
        self.page_settings.open_path_requested.connect(self._open_path)
        self.page_settings.clear_data_requested.connect(self._request_clear_local_data)
        self.page_jobs.outputs_ready.connect(self._on_outputs_ready)
        self.page_jobs.open_output_requested.connect(self._open_output_for_job)
        self._on_bridge_connection(self.bridge.connected, "本地桥接已就绪")
        self._update_nav_badges()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        mark = QLabel("R")
        mark.setObjectName("brandMark")
        brand_row.addWidget(mark, 0, Qt.AlignTop)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        title = QLabel("Resume Matcher")
        title.setObjectName("brandTitle")
        brand_copy.addWidget(title)
        subtitle = QLabel("自适应简历工作台")
        subtitle.setObjectName("brandSubtitle")
        brand_copy.addWidget(subtitle)
        brand_row.addLayout(brand_copy, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(9)

        role_label = QLabel("当前角色")
        role_label.setObjectName("navSection")
        layout.addWidget(role_label)
        self.role_button = QPushButton()
        self.role_button.setObjectName("roleCard")
        self.role_button.setCursor(Qt.PointingHandCursor)
        self.role_button.setToolTip("切换、创建或删除角色；每个角色隔离履历、岗位池和文字简历")
        self.role_button.clicked.connect(self._switch_role)
        role_layout = QHBoxLayout(self.role_button)
        role_layout.setContentsMargins(8, 6, 7, 6)
        role_layout.setSpacing(8)
        self.role_avatar = QLabel("?")
        self.role_avatar.setObjectName("roleAvatar")
        role_layout.addWidget(self.role_avatar)
        role_copy = QVBoxLayout()
        role_copy.setSpacing(0)
        self.role_name_label = ElidedLabel("未选择角色")
        self.role_name_label.setObjectName("roleName")
        role_copy.addWidget(self.role_name_label)
        self.role_meta_label = ElidedLabel("点击切换工作区")
        self.role_meta_label.setObjectName("roleMeta")
        role_copy.addWidget(self.role_meta_label)
        role_layout.addLayout(role_copy, 1)
        chevron = QLabel()
        chevron.setPixmap(themed_icon("chevron-down", 14).pixmap(14, 14))
        role_layout.addWidget(chevron)
        layout.addWidget(self.role_button)

        section = QLabel("工作区")
        section.setObjectName("navSection")
        layout.addWidget(section)
        self._nav_buttons = []
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (label, icon_name) in enumerate((
            ("个人履历", "user"),
            ("岗位工作台", "briefcase"),
            ("简历库", "file"),
            ("设置", "settings"),
        )):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(themed_icon(icon_name, 17))
            button.setIconSize(QSize(17, 17))
            button.setProperty("baseLabel", label)
            self.nav_group.addButton(button, index)
            self._nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_group.buttonClicked[int].connect(self._navigate)
        layout.addStretch(1)

        connection = QFrame()
        connection.setObjectName("connectionCard")
        connection_layout = QVBoxLayout(connection)
        connection_layout.setContentsMargins(9, 8, 9, 8)
        connection_layout.setSpacing(2)
        connection_head = QHBoxLayout()
        connection_head.setSpacing(5)
        self.connection_dot = QLabel("●")
        self.connection_dot.setObjectName("warning")
        connection_head.addWidget(self.connection_dot)
        connection_title = QLabel("浏览器采集")
        connection_title.setObjectName("connectionTitle")
        connection_head.addWidget(connection_title, 1)
        connection_layout.addLayout(connection_head)
        self.connection_meta = QLabel("等待扩展连接")
        self.connection_meta.setObjectName("connectionMeta")
        self.connection_meta.setWordWrap(True)
        connection_layout.addWidget(self.connection_meta)
        layout.addWidget(connection)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeRow")
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        self._refresh_theme_button()
        return sidebar

    def _nav_button(self, index: int) -> QPushButton:
        return self._nav_buttons[index]

    def _update_nav_badges(self):
        if not hasattr(self, "_nav_buttons"):
            return
        try:
            jobs_count = len([j for j in self.page_jobs.jobs if j.get("id") not in self.page_jobs.hidden_ids])
        except Exception:
            jobs_count = 0
        try:
            outputs_count = len(self.page_outputs.jobs)
        except Exception:
            outputs_count = 0
        for index, count in ((1, jobs_count), (2, outputs_count)):
            base = self._nav_buttons[index].property("baseLabel") or ""
            self._nav_buttons[index].setText(base + (("    %d" % count) if count else ""))


    def _build_log_dock(self):
        self.log_emitter = LogEmitter()
        self.log_emitter.message.connect(self._append_log)
        logging.getLogger("resume").addHandler(QtLogHandler(self.log_emitter))

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        self.log_panel = LogPanel()
        vbox.addWidget(self.log_panel)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.log_panel.clear)
        row.addWidget(btn_clear)
        vbox.addLayout(row)

        self.log_dock = QDockWidget("运行日志（出错时看这里）", self)
        self.log_dock.setWidget(panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.setVisible(False)

    # ------------------------------------------------------------ 槽
    def _on_progress(self, percent: int, message: str):
        self.progress.setValue(int(percent))
        if message:
            self.status_label.setText(message)

    def _on_status(self, message: str):
        self.status_label.setText(message)
        log.info("%s", message)

    def _on_bridge_failed(self, message: str):
        self.status_label.setText("本地桥接失败：%s" % message)
        log.error("本地桥接失败：%s", message)

    def _on_bridge_connection(self, connected: bool, text: str = ""):
        port = int(getattr(self.bridge, "port", 0) or 0)
        self.connection_dot.setObjectName("success" if connected else "warning")
        self.connection_dot.style().unpolish(self.connection_dot)
        self.connection_dot.style().polish(self.connection_dot)
        if connected:
            self.connection_meta.setText("127.0.0.1:%d\n采集扩展已连接" % port)
            self.connection_meta.setToolTip(text)
        else:
            self.connection_meta.setText("等待浏览器扩展连接")
            self.connection_meta.setToolTip(text or "打开已安装扩展的 BOSS 页面")
        self.page_settings.set_bridge_status(connected, port or None)

    def _on_outputs_ready(self):
        self.progress.setValue(100)
        self.page_outputs.refresh()
        self._update_nav_badges()
        self._navigate(2)

    def _open_output_for_job(self, job_id: str):
        self.page_outputs.refresh()
        if self.page_outputs.select_job(job_id):
            self._navigate(2)

    def _navigate(self, index: int, animate: bool = True):
        index = max(0, min(int(index), self.stack.count() - 1))
        current = self.stack.currentIndex()
        if current == 2 and index != 2:
            self.page_outputs.save_pending()
        if index == 2:
            self.page_outputs.refresh()
        elif index == 3:
            self.page_settings.reload()
        self.stack.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)
        self._update_nav_badges()
        if animate and current != index:
            fade_in(self.stack.currentWidget(), 140)

    def _append_log(self, text: str):
        self.log_panel.append_line(text)

    # ------------------------------------------------------------ 角色与主题
    def _update_role_chip(self):
        active = profiles.active_profile()
        if active:
            name = active.get("name") or "未命名角色"
            self.role_name_label.setText(name)
            self.role_meta_label.setText("个人工作区")
            self.role_avatar.setText(name[:1].upper())
            self.setWindowTitle("Resume Matcher · %s" % name)
            self.page_profile.set_role_name(name)
        else:
            self.role_name_label.setText("未选择角色")
            self.role_meta_label.setText("点击切换工作区")
            self.role_avatar.setText("?")
            self.setWindowTitle("Resume Matcher")
            self.page_profile.set_role_name("")

    def _current_role_dir(self):
        active = profiles.active_profile()
        if not active:
            return DATA_DIR
        return profiles.profile_paths(active["id"])["base"]

    def _current_jobs_dir(self):
        active = profiles.active_profile()
        if not active:
            return DATA_DIR / "jobs"
        return profiles.profile_paths(active["id"])["jobs_dir"]

    def _current_profile_file(self):
        active = profiles.active_profile()
        if not active:
            return DATA_DIR / "profile_text.json"
        return profiles.profile_paths(active["id"])["profile_text"]

    def _save_role_state(self) -> bool:
        if self.page_jobs.has_running_work:
            QMessageBox.warning(
                self, "任务进行中",
                "岗位遍历或批量任务尚未结束。请等待当前任务完成后再切换角色，"
                "避免结果写入错误的角色。",
            )
            return False
        try:
            ok_profile = self.page_profile.save_now(silent=True)
            ok_outputs = self.page_outputs.save_pending()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", "切换前保存数据失败：\n%s" % exc)
            return False
        if not (ok_profile and ok_outputs):
            QMessageBox.warning(self, "保存失败", "还有内容未保存，已取消角色切换。")
            return False
        return True

    def _refresh_after_profile_change(self):
        self.ctx.reload()
        self.page_profile.reload_for_profile()
        self.page_jobs.reload_for_profile()
        self.page_outputs.reload_for_profile()
        self.page_settings.reload()
        self._update_role_chip()
        self._update_nav_badges()
        self.progress.setValue(0)
        self.status_label.setText("已切换角色")

    def _switch_role(self):
        if not self._save_role_state():
            return
        dialog = RoleDialog(self, startup=False)
        if dialog.exec_() != dialog.Accepted or not dialog.selected_id:
            return
        try:
            profiles.activate_profile(dialog.selected_id)
        except Exception as exc:
            QMessageBox.critical(self, "切换失败", str(exc))
            return
        self._refresh_after_profile_change()
        self._on_status("已切换角色：%s" % self.role_name_label.text())

    def _new_role(self):
        if not self._save_role_state():
            return
        dialog = RoleDialog(self, startup=True)
        if dialog.exec_() != dialog.Accepted or not dialog.selected_id:
            return
        try:
            profiles.activate_profile(dialog.selected_id)
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        self._refresh_after_profile_change()
        self._on_status("已进入角色：%s" % self.role_name_label.text())

    def _logout_role(self):
        if not self._save_role_state():
            return
        old = profiles.active_profile()
        profiles.clear_active()
        dialog = RoleDialog(
            self, startup=True,
            protected_id=old["id"] if old else "",
        )
        if dialog.exec_() != dialog.Accepted or not dialog.selected_id:
            if old:
                profiles.activate_profile(old["id"])
                self._update_role_chip()
            return
        try:
            profiles.activate_profile(dialog.selected_id)
        except Exception as exc:
            QMessageBox.critical(self, "切换失败", str(exc))
            return
        self._refresh_after_profile_change()
        self._on_status("已切换角色：%s" % self.role_name_label.text())

    def _set_theme(self, mode: str):
        mode = mode if mode in ("system", "light", "dark") else "system"
        cfg = load_config()
        cfg.setdefault("ui", {})["theme"] = mode
        save_config(cfg)
        resolved = apply_theme(QApplication.instance(), mode)
        for action in self.theme_group.actions():
            action.setChecked(action.data() == mode)
        self.page_settings.set_theme(mode)
        for button, icon_name in zip(
            self._nav_buttons, ("user", "briefcase", "file", "settings")
        ):
            button.setIcon(themed_icon(icon_name, 17))
        self._refresh_theme_button()
        self._on_status("主题已切换：%s" % ("深色" if resolved == "dark" else "浅色"))

    def _refresh_theme_button(self):
        app = QApplication.instance()
        dark = bool(app and app.property("resolvedTheme") == "dark")
        self.theme_button.setText("切换到浅色主题" if dark else "切换到深色主题")
        self.theme_button.setIcon(themed_icon("sun" if dark else "moon", 16))

    def _toggle_theme(self):
        app = QApplication.instance()
        dark = bool(app and app.property("resolvedTheme") == "dark")
        self._set_theme("light" if dark else "dark")

    def _open_settings(self):
        self.page_settings.reload()
        self._navigate(3)

    def _request_clear_local_data(self):
        if self.page_jobs.has_running_work:
            QMessageBox.warning(
                self, "任务进行中",
                "岗位遍历或批量生成任务尚未结束。请先停止并等待当前任务结束，再清空本地数据。",
            )
            return
        dialog = ClearDataDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        self._clear_local_data(dialog.delete_config_requested())

    def _clear_local_data(self, include_config: bool = False):
        """Stop writers, delete app-owned data, then restart into first-run."""
        self._skip_close_save = True
        self.page_profile.suspend_saving()
        self.page_outputs.discard_pending()
        self.bridge.stop()
        shutdown_logging()

        error = ""
        report = None
        try:
            report = clear_local_data(include_config=include_config)
        except Exception as exc:
            error = str(exc)

        settings_error = ""
        try:
            settings = QSettings("ResumeMatcher", "ResumeMatcherDesktop")
            settings.clear()
            settings.sync()
        except Exception as exc:
            settings_error = str(exc)

        failures = (report or {}).get("failures") or []
        if error or failures or settings_error:
            box = QMessageBox(self)
            box.setWindowTitle("清空未完全完成")
            box.setIcon(QMessageBox.Warning)
            box.setText("部分本地数据未能删除，应用仍会重新启动。")
            details = [error, settings_error]
            details.extend(
                "%s：%s" % (item.get("path"), item.get("error"))
                for item in failures
            )
            box.setInformativeText(
                "请关闭可能占用文件的程序后，在设置中再次清空。\n"
                "如果问题持续，请查看下方详细信息。"
            )
            box.setDetailedText("\n".join(text for text in details if text))
            box.exec_()
        else:
            kept = "API Key 与模型配置已保留。" if not include_config else "API Key 与模型配置也已删除。"
            box = QMessageBox(self)
            box.setWindowTitle("本地数据已清空")
            box.setIcon(QMessageBox.Information)
            box.setText("所有角色与本地工作数据已清空。")
            box.setInformativeText(
                "%s\n应用将重新启动，并进入首次创建角色的流程。" % kept
            )
            box.exec_()

        self._restart_after_clear()

    def _restart_after_clear(self):
        program = sys.executable
        arguments = [] if getattr(sys, "frozen", False) else [str(APP_DIR / "main.py")]
        started, _pid = QProcess.startDetached(program, arguments, str(APP_DIR))
        if not started:
            QMessageBox.information(
                self, "请重新打开程序",
                "本地数据已处理完成。请手动重新打开本程序，以进入首次创建角色流程。",
            )
        self.close()

    def _open_path(self, path):
        try:
            os.startfile(str(path))
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))

    def _about(self):
        QMessageBox.about(
            self,
            "关于",
            "自适应简历生成器 V2\n\n"
            "浏览器遍历岗位后先做意向评分，再按所选岗位生成文字简历。\n"
            "角色之间完整隔离履历、岗位池与结果；生成前会本地审计可复用结果。\n"
            "个人履历使用一整段自由文本；支持精准 / 标准 / 委婉三档表达强弱。\n"
            "原则：只优化表达，不创造事实。\n\n"
            "接口：默认 DeepSeek（可在「接口设置」里更换）",
        )

    def _restore_window_state(self):
        settings = QSettings("ResumeMatcher", "ResumeMatcherDesktop")
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        try:
            page = min(self.stack.count() - 1, max(0, int(settings.value("window/page", 0))))
        except (TypeError, ValueError):
            page = 0
        self._navigate(page, animate=False)

    def _save_window_state(self):
        settings = QSettings("ResumeMatcher", "ResumeMatcherDesktop")
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/page", self.stack.currentIndex())

    def closeEvent(self, event):
        if self._skip_close_save:
            self.bridge.stop()
            super().closeEvent(event)
            return
        self.bridge.stop()
        try:
            ok_profile = self.page_profile.save_now(silent=True)
            ok_outputs = self.page_outputs.save_pending()
        except Exception:
            ok_profile = ok_outputs = False
        if not (ok_profile and ok_outputs):
            answer = QMessageBox.question(
                self, "保存失败", "还有内容未能保存到磁盘。\n是否仍然退出？"
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self._save_window_state()
        super().closeEvent(event)

    # ------------------------------------------------------------ 异常兜底
    def _install_excepthook(self):
        def hook(exc_type, exc_value, exc_tb):
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            log.error("未捕获异常：\n%s", text)
            try:
                QMessageBox.critical(self, "程序出错", "发生未预期的错误：\n%s\n\n详细信息见日志面板。" % exc_value)
            except Exception:
                pass

        sys.excepthook = hook


def main() -> int:
    setup_logging()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    cfg = load_config()
    theme_mode = str((cfg.get("ui") or {}).get("theme") or "system")
    apply_theme(app, theme_mode)

    if not profiles.active_profile():
        dialog = RoleDialog(None, startup=True)
        if dialog.exec_() != dialog.Accepted or not dialog.selected_id:
            return 0
        active = profiles.active_profile()
        if not active or active.get("id") != dialog.selected_id:
            profiles.activate_profile(dialog.selected_id)
    else:
        profiles.apply_active_profile()

    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
