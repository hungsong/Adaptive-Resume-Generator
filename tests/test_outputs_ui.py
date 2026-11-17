# -*- coding: utf-8 -*-
"""文字简历页：刷新和筛选后必须重新载入当前正文。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt5.QtWidgets import QApplication

from core import jobs
from ui.page_outputs import OutputsPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_refresh_loads_selected_resume_body(app, tmp_path, monkeypatch):
    pool = tmp_path / "jobs.json"
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", pool)
    jobs.save_pool([{
        "id": "job-a",
        "company": "甲公司",
        "title": "视觉工程师",
        "intent": {"score": 90},
        "tailored": {"text": "这是刷新后必须显示的文字简历正文。"},
    }])

    page = OutputsPage(ctx=None)
    assert page.list.count() == 1
    assert page.editor.toPlainText() == "这是刷新后必须显示的文字简历正文。"

    page.refresh()
    assert page.editor.toPlainText() == "这是刷新后必须显示的文字简历正文。"
    page.deleteLater()

