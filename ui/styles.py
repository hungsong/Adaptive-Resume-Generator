# -*- coding: utf-8 -*-
"""界面主题：Apple 式留白与字体层级 + Fluent 式分组与状态反馈。"""
from __future__ import annotations

from string import Template

THEME_MODES = ("system", "light", "dark")

LIGHT = {
    "bg": "#F4F5F7",
    "sidebar": "#EEF1F4",
    "surface": "#FFFFFF",
    "surface_alt": "#F8F9FB",
    "surface_hover": "#EFF2F5",
    "muted_fill": "#EDF0F3",
    "border": "#E0E4E9",
    "border_strong": "#C7CED6",
    "text": "#171A1F",
    "text_secondary": "#4F5968",
    "muted": "#657080",
    "accent": "#245EB8",
    "accent_hover": "#1E50A0",
    "accent_pressed": "#173F80",
    "accent_fill": "#245EB8",
    "accent_fill_hover": "#1E50A0",
    "accent_soft": "#E9F0FB",
    "selection": "#E7EFFB",
    "danger": "#C3362B",
    "danger_hover": "#A92C23",
    "danger_soft": "#FDECEA",
    "danger_button_text": "#FFFFFF",
    "warning": "#9A5A00",
    "warning_soft": "#FFF4E3",
    "success": "#157A4A",
    "success_soft": "#E8F5EE",
    "focus": "#6F9FF1",
    "disabled": "#98A1AE",
    "input": "#FFFFFF",
    "table_header": "#F8F9FB",
}

DARK = {
    "bg": "#0F1215",
    "sidebar": "#14181C",
    "surface": "#191E23",
    "surface_alt": "#20262C",
    "surface_hover": "#252C33",
    "muted_fill": "#232A31",
    "border": "#2D353D",
    "border_strong": "#47525E",
    "text": "#F1F4F6",
    "text_secondary": "#AFB8C2",
    "muted": "#94A0AD",
    "accent": "#6E9EFF",
    "accent_hover": "#8BB4FF",
    "accent_pressed": "#2859B5",
    "accent_fill": "#2F66D0",
    "accent_fill_hover": "#3B74E2",
    "accent_soft": "#162A46",
    "selection": "#1B3558",
    "danger": "#FF7B72",
    "danger_hover": "#FF958E",
    "danger_soft": "#3D1E1D",
    "danger_button_text": "#24100F",
    "warning": "#F0B35A",
    "warning_soft": "#382A14",
    "success": "#4DC58A",
    "success_soft": "#153327",
    "focus": "#7AA7FF",
    "disabled": "#6E7884",
    "input": "#1F252B",
    "table_header": "#181D22",
}

TEMPLATE = Template("""
QWidget {
    font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 10pt;
    color: $text;
}
QMainWindow, QDialog, QWidget#page { background: $bg; }
QWidget#pageSurface { background: $surface; }
QFrame#card, QGroupBox {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}
QGroupBox {
    margin-top: 18px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 5px;
    color: $text;
    background: $surface;
}
QFrame#hero {
    background: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}
QLabel { background: transparent; }
QLabel#pageTitle { font-size: 20pt; font-weight: 600; color: $text; }
QLabel#sectionTitle { font-size: 12pt; font-weight: 600; color: $text; }
QLabel#cardTitle { font-size: 11pt; font-weight: 600; color: $text; }
QLabel#metric { font-size: 17pt; font-weight: 600; color: $text; }
QLabel#muted, QLabel#hint { color: $muted; }
QLabel#hint { padding: 4px 0; }
QLabel#success { color: $success; font-weight: 600; }
QLabel#warning { color: $warning; font-weight: 600; }
QLabel#dangerText { color: $danger; }
QLabel#roleChip {
    color: $text_secondary;
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 14px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#roleChip {
    color: $text_secondary;
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 15px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton#roleChip:hover { background: $surface_hover; color: $text; }
QPushButton#roleChip:focus { border-color: $focus; }
QTabWidget::pane {
    border: none;
    background: $bg;
    top: -1px;
}
QTabBar::tab {
    padding: 9px 22px;
    margin-right: 6px;
    border: 1px solid transparent;
    border-radius: 9px;
    background: transparent;
    color: $text_secondary;
}
QTabBar::tab:hover { background: $surface_hover; color: $text; }
QTabBar::tab:selected {
    background: $surface;
    color: $accent;
    border-color: $border;
    font-weight: 600;
}
QPushButton {
    min-height: 20px;
    padding: 7px 14px;
    border: 1px solid $border;
    border-radius: 6px;
    background: $surface;
    color: $text;
}
QPushButton:hover { background: $surface_hover; border-color: $border_strong; }
QPushButton:pressed { background: $surface_alt; }
QPushButton:focus { border-color: $focus; }
QPushButton:disabled { color: $disabled; background: $surface_alt; border-color: $border; }
QPushButton#primary {
    background: $accent_fill;
    color: #FFFFFF;
    border: 1px solid $accent_fill;
    font-weight: 600;
}
QPushButton#primary:hover { background: $accent_fill_hover; border-color: $accent_fill_hover; }
QPushButton#primary:pressed { background: $accent_pressed; }
QPushButton#primary:disabled { background: $accent_soft; color: $disabled; border-color: transparent; }
QPushButton#secondary { background: $surface_alt; }
QPushButton#danger { color: $danger; border-color: $border; background: $surface; }
QPushButton#danger:hover { background: $danger_soft; border-color: $danger; }
QPushButton#danger:disabled { color: $disabled; border-color: $border; background: $surface_alt; }
QPushButton#dangerSolid {
    background: $danger; color: $danger_button_text; border: 1px solid $danger; font-weight: 600;
}
QPushButton#dangerSolid:hover { background: $danger_hover; border-color: $danger_hover; }
QPushButton#dangerSolid:disabled { background: $danger_soft; color: $disabled; border-color: $border; }
QPushButton#ghost { border-color: transparent; background: transparent; color: $text_secondary; }
QPushButton#ghost:hover { background: $surface_hover; color: $text; }
QPushButton#linkButton {
    border: none;
    background: transparent;
    color: $accent;
    padding: 2px 0;
    text-align: left;
}
QPushButton#linkButton:hover { color: $accent_hover; text-decoration: underline; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    border: 1px solid $border;
    border-radius: 6px;
    background: $input;
    color: $text;
    padding: 6px 8px;
    selection-background-color: $accent;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid $focus;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: $disabled;
    background: $surface_alt;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    selection-background-color: $selection;
    selection-color: $text;
    padding: 4px;
}
QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background: $input;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QListWidget, QTreeWidget, QTableWidget {
    border: 1px solid $border;
    border-radius: 10px;
    background: $surface;
    alternate-background-color: $surface_alt;
    gridline-color: $border;
    selection-background-color: $selection;
    selection-color: $text;
    outline: none;
}
QListWidget::item { padding: 9px 8px; border-radius: 6px; }
QListWidget::item:hover { background: $surface_hover; }
QListWidget::item:selected { background: $selection; color: $text; }
QTableWidget::item { padding: 5px 7px; border-bottom: 1px solid $border; }
QTableWidget::item:hover { background: $surface_hover; }
QTableWidget::item:selected { background: $selection; color: $text; }
QHeaderView::section {
    background: $table_header;
    color: $text_secondary;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
    padding: 8px 4px;
    font-size: 8.5pt;
    font-weight: 600;
}
QTableCornerButton::section { background: $table_header; border: none; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border_strong; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border_strong; min-width: 28px; border-radius: 4px; }
QProgressBar {
    border: 1px solid $border;
    border-radius: 5px;
    background: $surface_alt;
    text-align: center;
    min-height: 10px;
    max-height: 10px;
    color: transparent;
}
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QStatusBar { background: $surface; color: $text_secondary; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QMenuBar { background: $surface; border-bottom: 1px solid $border; }
QMenuBar::item { padding: 7px 10px; background: transparent; border-radius: 5px; }
QMenuBar::item:selected { background: $surface_hover; }
QMenu { background: $surface; border: 1px solid $border; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 24px; border-radius: 5px; }
QMenu::item:selected { background: $selection; }
QToolTip {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    padding: 6px;
}
QSplitter::handle { background: transparent; width: 8px; height: 8px; }
QDockWidget { color: $text_secondary; }
QDialogButtonBox QPushButton { min-width: 76px; }

/* ---------- desktop shell ---------- */
QWidget#appRoot { background: $bg; }
QFrame#appFooter { background: transparent; border-top: 1px solid $border; }
QLabel#footerStatus { color: $text_secondary; font-size: 8pt; }
QLabel#footerMeta { color: $muted; font-size: 8pt; }
QFrame#sidebar {
    background: $sidebar;
    border: none;
    border-right: 1px solid $border;
}
QLabel#brandTitle { font-size: 10.5pt; font-weight: 600; color: $text; }
QLabel#brandSubtitle { font-size: 8pt; color: $muted; }
QLabel#brandMark {
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    border-radius: 8px; background: $text; color: $surface;
    font-size: 12pt; font-weight: 700; qproperty-alignment: AlignCenter;
}
QLabel#navSection { font-size: 8pt; font-weight: 700; color: $muted; padding: 9px 9px 3px 9px; }
QPushButton#navButton {
    min-height: 36px; max-height: 36px; text-align: left;
    padding: 0 10px; border: 1px solid transparent; border-left: 2px solid transparent;
    border-radius: 6px; background: transparent; color: $text_secondary;
    font-size: 10pt; font-weight: 500;
}
QPushButton#navButton:hover { background: $surface_hover; color: $text; }
QPushButton#navButton:checked {
    background: $accent_soft; color: $accent; border-color: transparent;
    border-left: 2px solid $accent; font-weight: 600;
}
QPushButton#roleCard {
    min-height: 46px; text-align: left; padding: 7px 9px;
    border: 1px solid $border; border-radius: 8px; background: $surface; color: $text;
}
QPushButton#roleCard:hover { background: $surface_hover; border-color: $border_strong; }
QLabel#roleAvatar {
    min-width: 27px; max-width: 27px; min-height: 27px; max-height: 27px;
    border-radius: 7px; background: $accent_soft; color: $accent;
    font-weight: 700; qproperty-alignment: AlignCenter;
}
QLabel#roleName { font-size: 9.5pt; font-weight: 600; color: $text; }
QLabel#roleMeta { font-size: 8pt; color: $muted; }
QFrame#connectionCard { background: $surface_alt; border: 1px solid $border; border-radius: 8px; }
QLabel#connectionTitle { font-size: 8.5pt; font-weight: 600; color: $text; }
QLabel#connectionMeta { font-size: 8pt; color: $muted; font-family: "Cascadia Code", "Consolas"; }
QPushButton#themeRow {
    min-height: 31px; text-align: left; padding: 0 9px; border: 1px solid transparent;
    border-radius: 6px; background: transparent; color: $text_secondary; font-size: 9pt;
}
QPushButton#themeRow:hover { background: $surface_hover; color: $text; }

/* ---------- page hierarchy ---------- */
QLabel#pageEyebrow {
    font-size: 7.5pt; font-weight: 700; color: $muted;
}
QLabel#pageTitle { font-size: 19pt; font-weight: 600; color: $text; }
QLabel#pageSubtitle { font-size: 9.5pt; color: $text_secondary; }
QLabel#sectionKicker { font-size: 7.5pt; font-weight: 700; color: $muted; }
QLabel#sectionTitle { font-size: 11pt; font-weight: 600; color: $text; }
QLabel#cardTitle { font-size: 10pt; font-weight: 600; color: $text; }
QLabel#smallLabel { font-size: 8pt; color: $muted; }
QLabel#smallValue { font-size: 9pt; font-weight: 600; color: $text; }
QLabel#emptyTitle { font-size: 11pt; font-weight: 600; color: $text; }
QLabel#emptyBody { font-size: 9pt; color: $muted; }
QFrame#divider { background: $border; border: none; max-height: 1px; }

/* ---------- chips and compact states ---------- */
QLabel#chipSuccess, QLabel#chipWarning, QLabel#chipDanger, QLabel#chipNeutral, QLabel#chipAccent {
    min-height: 19px; max-height: 19px; padding: 0 6px; border-radius: 9px;
    font-size: 8pt; font-weight: 600;
}
QLabel#chipSuccess { color: $success; background: $success_soft; }
QLabel#chipWarning { color: $warning; background: $warning_soft; }
QLabel#chipDanger { color: $danger; background: $danger_soft; }
QLabel#chipNeutral { color: $text_secondary; background: $muted_fill; }
QLabel#chipAccent { color: $accent; background: $accent_soft; }
QLabel#tableChipSuccess, QLabel#tableChipWarning, QLabel#tableChipDanger,
QLabel#tableChipNeutral, QLabel#tableChipAccent {
    min-height: 17px; max-height: 18px; padding: 0 4px; border-radius: 4px;
    font-size: 7.5pt; font-weight: 600;
}
QLabel#tableChipSuccess { color: $success; background: $success_soft; }
QLabel#tableChipWarning { color: $warning; background: $warning_soft; }
QLabel#tableChipDanger { color: $danger; background: $danger_soft; }
QLabel#tableChipNeutral { color: $text_secondary; background: $muted_fill; }
QLabel#tableChipAccent { color: $accent; background: $accent_soft; }

/* ---------- desktop controls ---------- */
QPushButton#iconButton {
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    padding: 0; border: 1px solid transparent; border-radius: 6px; background: transparent;
}
QPushButton#iconButton:hover { background: $surface_hover; border-color: $border; }
QLineEdit#searchField { padding-left: 6px; min-height: 30px; max-height: 30px; font-size: 9pt; }
QFrame#segmented { background: $surface_alt; border: 1px solid $border; border-radius: 7px; }
QPushButton#segmentButton {
    min-height: 26px; max-height: 26px; padding: 0 8px; border: 1px solid transparent;
    border-radius: 5px; background: transparent; color: $muted; font-size: 8.5pt;
}
QPushButton#segmentButton:hover { color: $text; }
QPushButton#segmentButton:checked { background: $surface; color: $text; border-color: $border; font-weight: 600; }

/* ---------- profile page ---------- */
QFrame#editorCard, QFrame#documentCard, QFrame#tableCard, QFrame#settingsCard, QFrame#criteriaCard {
    background: $surface; border: 1px solid $border; border-radius: 8px;
}
QLabel#editorState { font-size: 8pt; color: $muted; }
QPlainTextEdit#profileEditor {
    border: 0; border-radius: 0; padding: 18px 20px; background: $surface;
    color: $text; font-size: 11pt;
}
QPlainTextEdit#profileEditor:focus { border: 0; }
QFrame#editorToolbar { background: $surface; border-radius: 8px 8px 0 0; }
QProgressBar#profileProgress { min-height: 4px; max-height: 5px; border: 0; border-radius: 3px; background: $muted_fill; }
QProgressBar#profileProgress::chunk { background: $accent; border-radius: 3px; }
QFrame#editorFooter { background: $surface_alt; border-top: 1px solid $border; border-radius: 0 0 8px 8px; }
QLabel#editorFooterText { font-size: 8pt; color: $muted; }
QLabel#savedState { font-size: 8pt; color: $success; font-weight: 600; }
QFrame#railCard { background: $surface; border: 1px solid $border; border-radius: 8px; }
QFrame#railCardQuiet { background: $surface_alt; border: 1px solid $border; border-radius: 8px; }
QLabel#railTitle { font-size: 9pt; font-weight: 600; color: $text; }
QLabel#railBody { font-size: 8.5pt; color: $text_secondary; }
QLabel#checkLine { font-size: 8pt; color: $text_secondary; }
QProgressBar#completionBar { min-height: 4px; max-height: 5px; border: 0; border-radius: 3px; background: $muted_fill; }
QProgressBar#completionBar::chunk { background: $accent; border-radius: 3px; }

/* ---------- job workbench ---------- */
QFrame#scanbar, QFrame#scanCard { background: $surface; border: 1px solid $border; border-radius: 8px; }
QLabel#scanMetric { font-size: 11pt; font-weight: 600; color: $text; font-family: "Cascadia Code", "Consolas"; }
QLabel#scanMetricLabel { font-size: 7.5pt; color: $muted; }
QLabel#browserMark {
    min-width: 29px; max-width: 29px; min-height: 29px; max-height: 29px;
    border-radius: 7px; background: $accent_soft; color: $accent;
    font-size: 10pt; font-weight: 700; qproperty-alignment: AlignCenter;
}
QLabel#scanTitle { font-size: 9pt; font-weight: 600; color: $text; }
QLabel#scanMeta { font-size: 8pt; color: $muted; }
QLabel#statValue { font-size: 10pt; font-weight: 600; color: $text; font-family: "Cascadia Code", "Consolas"; }
QLabel#statLabel { font-size: 7.5pt; color: $muted; }
QLabel#criteriaTitle { font-size: 10pt; font-weight: 600; color: $text; }
QScrollArea#criteriaScroll { background: transparent; border: none; }
QWidget#criteriaBody { background: transparent; }
QScrollArea#inspectorScroll { background: transparent; border: none; }
QScrollArea#inspectorScroll > QWidget > QWidget { background: transparent; }
QWidget#inspectorHolder, QWidget#inspectorEmpty, QWidget#inspectorContent {
    background: transparent;
}
QLabel#fieldLabel { font-size: 8pt; font-weight: 600; color: $text_secondary; }
QLabel#fieldHelp { font-size: 7.5pt; color: $muted; }
QLabel#exampleHint {
    background: $surface_alt; border: 1px solid $border; border-radius: 5px;
    color: $muted; font-size: 7.5pt; padding: 7px 8px;
}
QFrame#criteriaFooter { background: $surface; border-top: 1px solid $border; border-radius: 0 0 8px 8px; }
QFrame#tableToolbar { background: $surface; border-bottom: 1px solid $border; border-radius: 8px 8px 0 0; }
QLabel#tableTitle { font-size: 10pt; font-weight: 600; color: $text; }
QLabel#tableMeta { font-size: 8pt; color: $muted; }
QTableWidget#jobTable {
    border: 0; border-radius: 0; background: $surface; alternate-background-color: $surface;
    gridline-color: transparent; selection-background-color: $selection; selection-color: $text;
}
QTableWidget#jobTable::item { padding: 4px 7px; border-bottom: 1px solid $border; }
QTableWidget#jobTable::item:hover { background: $surface_hover; }
QTableWidget#jobTable::item:selected { background: $selection; color: $text; }
QLabel#jobTitle { font-size: 9pt; font-weight: 600; color: $text; }
QLabel#jobTitleLink { font-size: 9pt; font-weight: 600; color: $text; }
QLabel#jobCompany, QLabel#jobSubValue { font-size: 7.5pt; color: $muted; }
QWidget#jobCell { background: transparent; }
QLabel#scoreValue { font-family: "Cascadia Code", "Consolas"; font-size: 9.5pt; font-weight: 600; color: $text; }
QLabel#scoreHigh { font-family: "Cascadia Code", "Consolas"; font-size: 9.5pt; font-weight: 600; color: $success; }
QLabel#scoreMuted { font-family: "Cascadia Code", "Consolas"; font-size: 9.5pt; font-weight: 600; color: $muted; }
QFrame#bulkbar { background: $surface_alt; border-top: 1px solid $border; border-radius: 0 0 8px 8px; }
QLabel#selectionMeta { font-size: 8pt; color: $text_secondary; }
QFrame#inspector { background: $surface; border: 1px solid $border; border-radius: 8px; }
QLabel#inspectorTitle { font-size: 13pt; font-weight: 600; color: $text; }
QLabel#inspectorCompany { font-size: 8.5pt; color: $text_secondary; }
QLabel#inspectorMeta { font-size: 8pt; color: $muted; }
QLabel#inspectorBody { font-size: 8.5pt; color: $text_secondary; }
QLabel#scoreRowLabel { font-size: 8pt; color: $text_secondary; }
QLabel#scoreRowValue { font-size: 8pt; color: $text_secondary; font-family: "Cascadia Code", "Consolas"; }
QProgressBar#scoreBar { min-height: 4px; max-height: 4px; border: 0; border-radius: 2px; background: $muted_fill; }
QProgressBar#scoreBar::chunk { background: $accent; border-radius: 2px; }

/* ---------- outputs ---------- */
QLabel#documentTitle { font-size: 15pt; font-weight: 600; color: $text; }
QLabel#documentMeta { font-size: 8.5pt; color: $text_secondary; }
QFrame#validationBanner { background: $success_soft; border-bottom: 1px solid $border; }
QFrame#validationWarning { background: $warning_soft; border-bottom: 1px solid $border; }
QLabel#validationText { font-size: 8pt; color: $text_secondary; }
QPlainTextEdit#documentEditor {
    border: 0; border-radius: 0; background: $surface; color: $text;
    font-size: 10.5pt; padding: 22px 46px;
}
QPlainTextEdit#documentEditor:focus { border: 0; }
QFrame#documentFooter { background: $surface_alt; border-top: 1px solid $border; border-radius: 0 0 8px 8px; }
QListWidget#outputList { border: 0; background: transparent; }
QListWidget#outputList::item { border: 1px solid transparent; border-radius: 6px; padding: 8px; margin: 1px 4px; }
QListWidget#outputList::item:hover { background: $surface_hover; }
QListWidget#outputList::item:selected { background: $accent_soft; color: $text; border-color: $border; }

/* ---------- settings ---------- */
QLabel#settingsTitle { font-size: 11pt; font-weight: 600; color: $text; }
QLabel#settingsBody { font-size: 8.5pt; color: $muted; }
QPushButton#themeOption {
    min-height: 64px; text-align: left; padding: 9px 10px;
    border: 1px solid $border; border-radius: 7px; background: $surface; color: $text;
}
QPushButton#themeOption:hover { background: $surface_hover; border-color: $border_strong; }
QPushButton#themeOption:checked { background: $accent_soft; border-color: $accent; color: $accent; }
QFrame#infoGrid { background: $surface_alt; border: 1px solid $border; border-radius: 7px; }
QFrame#pathRow { background: $surface_alt; border: 1px solid $border; border-radius: 6px; }
QWidget#settingsHolder { background: transparent; }
QFrame#dangerZone { background: $danger_soft; border: 1px solid $danger; border-radius: 7px; }
QLabel#dangerZoneTitle { font-size: 9pt; font-weight: 600; color: $danger; }
QLabel#dangerZoneBody { font-size: 8pt; color: $text_secondary; }
QDialog#clearDataDialog { background: $bg; }
QLabel#dangerDialogTitle { font-size: 14pt; font-weight: 600; color: $text; }
QLabel#dangerDialogSubtitle { font-size: 9pt; color: $text_secondary; }
QFrame#dangerNotice { background: $danger_soft; border: 1px solid $danger; border-radius: 7px; }
QLabel#dangerNoticeTitle { font-size: 9pt; font-weight: 600; color: $danger; }
QLabel#dangerNoticeBody { font-size: 8.5pt; color: $text_secondary; }
""")


def detect_system_theme() -> str:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:
        return "light"


def resolve_theme(mode: str | None) -> str:
    value = str(mode or "system").lower()
    if value not in THEME_MODES:
        value = "system"
    return detect_system_theme() if value == "system" else value


def build_qss(theme: str) -> str:
    tokens = DARK if str(theme).lower() == "dark" else LIGHT
    return TEMPLATE.safe_substitute(tokens)


def apply_theme(app, mode: str = "system") -> str:
    resolved = resolve_theme(mode)
    app.setStyleSheet(build_qss(resolved))
    app.setProperty("resolvedTheme", resolved)
    return resolved


# 兼容旧入口；应用启动后由 apply_theme 覆盖。
QSS = build_qss("light")
