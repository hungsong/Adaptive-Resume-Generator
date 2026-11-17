# -*- coding: utf-8 -*-
"""Reusable desktop UI primitives used across the four main pages."""
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ui.icons import themed_icon


class Card(QFrame):
    def __init__(self, parent=None, object_name: str = "card"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.NoFrame)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)


class ChipLabel(QLabel):
    VARIANTS = {"success", "warning", "danger", "neutral", "accent"}

    def __init__(self, text: str = "", variant: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_variant(variant)

    def set_variant(self, variant: str):
        variant = variant if variant in self.VARIANTS else "neutral"
        self.setObjectName("chip" + variant.capitalize())
        self.style().unpolish(self)
        self.style().polish(self)


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str = "", parent=None, size: int = 32):
        super().__init__(parent)
        self.setObjectName("iconButton")
        self.setFixedSize(size, size)
        self.setIconSize(QSize(16, 16))
        self.setIcon(themed_icon(icon_name, 16))
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "搜索…", parent=None):
        super().__init__(parent)
        self.setObjectName("searchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(themed_icon("search", 15), QLineEdit.LeadingPosition)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", eyebrow: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        if eyebrow:
            label = QLabel(eyebrow)
            label.setObjectName("pageEyebrow")
            copy.addWidget(label)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        copy.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        copy.addWidget(self.subtitle_label)
        layout.addLayout(copy, 1)
        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 2, 0, 0)
        self.actions.setSpacing(7)
        layout.addLayout(self.actions)

    def add_action(self, button: QPushButton):
        self.actions.addWidget(button)
        return button


class SegmentedControl(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, items, value: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons = []
        for key, label in items:
            button = QPushButton(label)
            button.setObjectName("segmentButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("segmentValue", key)
            button.clicked.connect(lambda _checked=False, k=key: self.changed.emit(k))
            self.group.addButton(button)
            self._buttons.append(button)
            layout.addWidget(button, 1)
        self.set_value(value or (items[0][0] if items else ""))

    def set_value(self, value: str):
        for button in self._buttons:
            button.setChecked(button.property("segmentValue") == value)

    def value(self) -> str:
        for button in self._buttons:
            if button.isChecked():
                return str(button.property("segmentValue"))
        return ""


class LabeledValue(QWidget):
    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.label = QLabel(label)
        self.label.setObjectName("smallLabel")
        layout.addWidget(self.label)
        self.value = QLabel(value)
        self.value.setObjectName("smallValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.value)

    def set_value(self, text: str):
        self.value.setText(text or "—")


class ElidedLabel(QLabel):
    """A label that keeps long paths readable without expanding its layout."""

    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.set_text(text)

    def setText(self, text: str):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._update_elision()

    def set_text(self, text: str):
        self.setText(text)

    def full_text(self) -> str:
        return self._full_text

    def minimumSizeHint(self) -> QSize:
        return QSize(0, QLabel.minimumSizeHint(self).height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elision()

    def _update_elision(self):
        width = self.contentsRect().width()
        if width <= 0:
            QLabel.setText(self, self._full_text)
            return
        elided = QFontMetrics(self.font()).elidedText(
            self._full_text, Qt.ElideMiddle, width
        )
        QLabel.setText(self, elided)


class EmptyState(QWidget):
    def __init__(self, title: str, body: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)
        layout.addStretch(1)
        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        body_label = QLabel(body)
        body_label.setObjectName("emptyBody")
        body_label.setAlignment(Qt.AlignCenter)
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        layout.addStretch(1)


def primary_button(text: str, icon_name: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("primary")
    if icon_name:
        button.setIcon(themed_icon(icon_name, 15))
    return button


def secondary_button(text: str, icon_name: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("secondary")
    if icon_name:
        button.setIcon(themed_icon(icon_name, 15))
    return button


def ghost_button(text: str, icon_name: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("ghost")
    if icon_name:
        button.setIcon(themed_icon(icon_name, 15))
    return button
