# -*- coding: utf-8 -*-
"""逐岗位导出：每个 Word / Markdown / Excel 文件必须独立且内容对应。"""
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from core import export_resumes


def _job(job_id: str, company: str, title: str, text: str) -> dict:
    return {
        "id": job_id,
        "company": company,
        "title": title,
        "city": "苏州",
        "salary": "20-30K",
        "url": "https://www.zhipin.com/job_detail/%s.html" % job_id,
        "intent": {"score": 88},
        "tailored": {
            "text": text,
            "sections": [{"title": "工作经历", "items": [{"text": text}]}],
        },
    }


@pytest.fixture()
def jobs():
    return [
        _job("aaaa1111", "甲公司", "视觉工程师", "甲公司专属的机器视觉交付经历。"),
        _job("bbbb2222", "乙公司", "设备工程师", "乙公司专属的现场设备排障经历。"),
    ]


@pytest.mark.parametrize("fmt,ext", [("docx", ".docx"), ("md", ".md"), ("xlsx", ".xlsx")])
def test_export_jobs_creates_one_independent_file_per_job(tmp_path, jobs, fmt, ext):
    target = tmp_path / "自定义导出路径"
    report = export_resumes.export_jobs(jobs, target, fmt)

    assert report["failures"] == []
    assert len(report["exported"]) == 2
    files = sorted(target.glob("*" + ext))
    assert len(files) == 2
    assert len({path.name for path in files}) == 2
    assert all(path.parent == target for path in files)

    if fmt == "docx":
        paragraphs = []
        for path in files:
            document = Document(str(path))
            paragraphs.append("\n".join(p.text for p in document.paragraphs))
        assert any("甲公司专属" in text for text in paragraphs)
        assert any("乙公司专属" in text for text in paragraphs)
    elif fmt == "md":
        contents = [path.read_text(encoding="utf-8") for path in files]
        assert any("甲公司专属" in text for text in contents)
        assert any("乙公司专属" in text for text in contents)
    else:
        values = []
        for path in files:
            sheet = load_workbook(str(path), read_only=True).active
            values.append("\n".join(str(cell.value or "") for row in sheet.iter_rows() for cell in row))
        assert any("甲公司专属" in text for text in values)
        assert any("乙公司专属" in text for text in values)


def test_export_failure_does_not_block_other_jobs(tmp_path, jobs):
    jobs.append({"id": "cccc3333", "company": "丙公司", "title": "空结果"})
    report = export_resumes.export_jobs(jobs, tmp_path, "docx")
    assert len(report["exported"]) == 2
    assert len(report["failures"]) == 1
    assert report["failures"][0]["job"] == "空结果"


def test_filename_is_windows_safe_and_uses_short_id(tmp_path):
    job = _job("id/with:bad*chars", "A/B:C", "设备*工程师?", "有效文字简历")
    path = export_resumes.export_one(job, tmp_path, "md")
    assert path.parent == tmp_path
    assert path.suffix == ".md"
    assert not any(char in path.name for char in '<>:"/\\|?*')
    assert "idwithba" in path.name

