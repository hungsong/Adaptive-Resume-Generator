# -*- coding: utf-8 -*-
"""克制的界面微动效：只用于页面与对话框出现时的淡入。"""
from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation
from PyQt5.QtWidgets import QGraphicsOpacityEffect


def fade_in(widget, duration: int = 180) -> None:
    if widget is None:
        return
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(max(80, int(duration)))
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    widget._fade_animation = animation
    animation.start()
