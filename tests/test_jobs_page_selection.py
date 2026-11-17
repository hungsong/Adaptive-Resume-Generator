# -*- coding: utf-8 -*-
"""岗位页勾选状态：排序、筛选和清空选择必须保持同步。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from core import intent, jobs
from ui.page_jobs import JobPoolPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_selection_survives_sort_and_filter(app, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_POOL_PATH", tmp_path / "jobs.json")
    monkeypatch.setattr(jobs, "HIDDEN_JOBS_PATH", tmp_path / "hidden.json")
    monkeypatch.setattr(intent, "load_criteria", lambda: intent.normalize_criteria({}))
    jobs.save_pool([
        {
            "id": "job-a", "title": "甲岗位", "company": "甲公司",
            "scanned_at": "2026-11-15 10:00:00",
            "intent": {"status": "recommended", "score": 60},
        },
        {
            "id": "job-b", "title": "乙岗位", "company": "乙公司",
            "scanned_at": "2026-11-15 09:00:00",
            "intent": {"status": "recommended", "score": 90},
        },
        {
            "id": "job-c", "title": "丙岗位", "company": "丙公司",
            "scanned_at": "2026-11-15 08:00:00",
            "intent": {"status": "rejected", "score": 20},
        },
    ])

    page = JobPoolPage(None)
    page.table.item(0, 0).setCheckState(Qt.Checked)
    app.processEvents()

    assert page._selected_ids() == ["job-a"]
    assert "已选择 1 个岗位" in page.selection_meta.text()
    assert page.btn_tailor.isEnabled()

    page.sort.setCurrentIndex(page.sort.findData("score"))
    app.processEvents()
    assert page._selected_ids() == ["job-a"]
    row_a = next(i for i, job in enumerate(page._rows) if job.get("id") == "job-a")
    assert page.table.item(row_a, 0).checkState() == Qt.Checked

    page.filter.setCurrentIndex(page.filter.findData("rejected"))
    app.processEvents()
    assert page._selected_ids() == ["job-a"]
    assert "1 个在当前筛选外" in page.selection_meta.text()
    assert page.btn_tailor.isEnabled()

    page._check_all(False)
    app.processEvents()
    assert page._selected_ids() == []
    assert page.selection_meta.text() == "未选择岗位"
    assert not page.btn_tailor.isEnabled()
    page.deleteLater()
