# -*- coding: utf-8 -*-
"""数值框和下拉框防误触：滚轮始终不能改变当前值。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QLineEdit

from ui.widgets import NoWheelComboBox, NoWheelSpinBox


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wheel_event(delta: int) -> QWheelEvent:
    position = QPointF(8, 8)
    return QWheelEvent(
        position,
        position,
        QPoint(),
        QPoint(0, delta),
        0,
        Qt.Vertical,
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
    )


def _combo_with_items() -> NoWheelComboBox:
    combo = NoWheelComboBox()
    combo.addItems(["精准", "标准", "委婉"])
    combo.setCurrentIndex(0)
    combo.resize(120, 32)
    combo.show()
    return combo


def test_wheel_does_not_change_combo_without_focus(app):
    combo = _combo_with_items()
    other = QLineEdit()
    other.show()
    other.setFocus()
    app.processEvents()
    assert not combo.hasFocus()

    QApplication.sendEvent(combo, _wheel_event(120))
    app.processEvents()
    assert combo.currentIndex() == 0

    combo.close()
    other.close()


def test_wheel_does_not_change_combo_even_after_focus(app):
    combo = _combo_with_items()
    combo.setFocus()
    app.processEvents()
    assert combo.hasFocus()

    QApplication.sendEvent(combo, _wheel_event(-120))
    app.processEvents()
    assert combo.currentIndex() == 0

    QTest.keyClick(combo, Qt.Key_Down)
    app.processEvents()
    assert combo.currentIndex() == 1

    combo.close()


def test_wheel_does_not_change_spinbox_even_after_focus(app):
    spin = NoWheelSpinBox()
    spin.setRange(0, 100)
    spin.setValue(62)
    spin.resize(120, 32)
    spin.show()
    spin.setFocus()
    app.processEvents()
    assert spin.hasFocus()

    QApplication.sendEvent(spin, _wheel_event(120))
    app.processEvents()
    assert spin.value() == 62

    QTest.keyClick(spin, Qt.Key_Up)
    app.processEvents()
    assert spin.value() == 63

    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), "75")
    spin.interpretText()
    assert spin.value() == 75

    spin.close()
