# -*- coding: utf-8 -*-
"""渲染测试：HTML / Markdown 结构正确，PDF 能真正写出来。"""
import os
from pathlib import Path

import pytest

from core import models, render

DOC = {
    "header": {"name": "张三", "phone": "13800000000", "email": "a@b.com", "city": "苏州",
               "target": "机器视觉工程师", "links": "github.com/zhangsan"},
    "summary": "3 年机器视觉现场调试经验。",
    "sections": [
        {"key": "work", "title": "工作经历", "items": [
            {"entry_id": "w1", "org": "某某自动化", "role": "视觉工程师",
             "start": "2020.03", "end": "2023.05",
             "bullets": [{"text": "完成客户现场设备调试", "evidence_ids": ["w1"], "flagged": False},
                         {"text": "独立完成 12 个项目选型", "evidence_ids": ["w1"], "flagged": True}]}]},
        {"key": "skills", "title": "技能", "items": [
            {"text": "机器视觉", "evidence_ids": ["s1"], "flagged": False},
            {"text": "PLC", "evidence_ids": ["s2"], "flagged": False}]},
    ],
}


def test_html_contains_key_parts():
    html = render.build_html(DOC)
    assert "张三" in html
    assert "工作经历" in html
    assert "完成客户现场设备调试" in html
    assert "待核实" in html


def test_html_can_hide_flags():
    assert "待核实" not in render.build_html(DOC, show_flags=False)


def test_markdown_structure():
    md = render.build_markdown(DOC)
    assert md.startswith("# 张三")
    assert "## 技能" in md
    assert "- 完成客户现场设备调试" in md


def test_export_markdown(tmp_path):
    path = render.export_markdown(DOC, tmp_path / "r.md")
    assert Path(path).read_text(encoding="utf-8").strip()


def test_export_pdf(tmp_path):
    # 不强制 offscreen：Windows 上 Qt 打印子系统在 offscreen 模式会触发 COM 错误
    from PyQt5.QtWidgets import QApplication

    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # 没有图形环境时跳过，不阻塞其它测试
        pytest.skip("无法创建 QApplication：%s" % exc)
    assert app is not None
    out = tmp_path / "r.pdf"
    render.export_pdf(render.build_html(DOC, show_flags=False), out)
    assert out.exists() and out.stat().st_size > 1000
