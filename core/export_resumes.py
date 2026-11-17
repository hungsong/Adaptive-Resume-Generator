# -*- coding: utf-8 -*-
"""把每个岗位的文字简历导出为独立文件。

每个岗位一个 Word / Markdown / Excel 文件，不做多岗位合订，避免 Word 中
无法可靠拆分章节。文件名形如 ``公司_岗位_短ID.docx``。
"""
from __future__ import annotations

import re
from pathlib import Path

from core.applog import get_logger

log = get_logger("export_resumes")

FORMAT_LABELS = {
    "docx": "Word 文档 (*.docx)",
    "md": "Markdown (*.md)",
    "xlsx": "Excel 工作簿 (*.xlsx)",
}
FORMAT_EXTENSIONS = {"docx": ".docx", "md": ".md", "xlsx": ".xlsx"}


def _clean_text(value) -> str:
    return str(value or "").strip()


def safe_filename(value: str, fallback: str = "未命名") -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", _clean_text(value))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text or fallback)[:80].rstrip(" .") or fallback


def base_filename(job: dict) -> str:
    company = safe_filename(job.get("company"), "")
    title = safe_filename(job.get("title"), "未命名岗位")
    short_id = re.sub(r"[^A-Za-z0-9_-]", "", _clean_text(job.get("id")))[:8]
    parts = [part for part in (company, title, short_id) if part]
    return safe_filename("_".join(parts), "未命名岗位_%s" % (short_id or "job"))


def resume_text(job: dict) -> str:
    tailored = job.get("tailored") if isinstance(job.get("tailored"), dict) else {}
    return _clean_text(tailored.get("text") or tailored.get("plain_text"))


def _sections(job: dict) -> list:
    tailored = job.get("tailored") if isinstance(job.get("tailored"), dict) else {}
    sections = tailored.get("sections") or []
    return sections if isinstance(sections, list) else []


def _section_items(section: dict) -> list:
    items = section.get("items") or []
    values = []
    for item in items:
        text = item.get("text") if isinstance(item, dict) else item
        text = _clean_text(text)
        if text:
            values.append(text)
    return values


def _markdown(job: dict) -> str:
    sections = _sections(job)
    if sections:
        lines = []
        for section in sections:
            title = _clean_text(section.get("title")) or "未命名章节"
            items = _section_items(section)
            if not items:
                continue
            if lines:
                lines.append("")
            lines.extend(["## " + title, ""])
            lines.extend("- " + item for item in items)
        if lines:
            return "\n".join(lines).strip() + "\n"
    return resume_text(job) + ("\n" if resume_text(job) else "")


def _write_markdown(job: dict, path: Path) -> None:
    path.write_text(_markdown(job), encoding="utf-8")


def _write_word(job: dict, path: Path) -> None:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(10.5)

    sections = _sections(job)
    if sections:
        wrote = False
        for section in sections:
            title = _clean_text(section.get("title")) or "未命名章节"
            items = _section_items(section)
            if not items:
                continue
            document.add_heading(title, level=1)
            for item in items:
                document.add_paragraph(item, style="List Bullet")
            wrote = True
        if not wrote:
            raise ValueError("该岗位没有可导出的简历章节")
    else:
        text = resume_text(job)
        if not text:
            raise ValueError("该岗位没有可导出的文字简历")
        for line in text.splitlines():
            value = line.strip()
            if value:
                document.add_paragraph(value[2:].strip() if value.startswith("- ") else value)
    document.save(str(path))


def _write_excel(job: dict, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "文字简历"
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 100

    meta = [
        ("公司", job.get("company") or ""),
        ("岗位", job.get("title") or ""),
        ("城市", job.get("city") or ""),
        ("薪资", job.get("salary") or ""),
        ("意向分", (job.get("intent") or {}).get("score") or ""),
        ("原岗位", job.get("url") or ""),
    ]
    for row, (label, value) in enumerate(meta, start=1):
        sheet.cell(row=row, column=1, value=label).font = Font(bold=True)
        sheet.cell(row=row, column=2, value=value)

    current = len(meta) + 2
    sections = _sections(job)
    if sections:
        for section in sections:
            items = _section_items(section)
            if not items:
                continue
            title = _clean_text(section.get("title")) or "未命名章节"
            title_cell = sheet.cell(row=current, column=1, value=title)
            title_cell.font = Font(bold=True, color="FFFFFF")
            title_cell.fill = PatternFill("solid", fgColor="4472C4")
            sheet.merge_cells(start_row=current, start_column=1, end_row=current, end_column=2)
            current += 1
            for item in items:
                sheet.cell(row=current, column=1, value="内容")
                cell = sheet.cell(row=current, column=2, value=item)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                current += 1
    else:
        text = resume_text(job)
        if not text:
            raise ValueError("该岗位没有可导出的文字简历")
        for line in text.splitlines():
            value = line.strip()
            if not value:
                continue
            sheet.cell(row=current, column=1, value="内容")
            cell = sheet.cell(row=current, column=2, value=value[2:].strip() if value.startswith("- ") else value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            current += 1
    workbook.save(str(path))


def export_one(job: dict, folder, fmt: str) -> Path:
    fmt = str(fmt or "").lower()
    if fmt not in FORMAT_EXTENSIONS:
        raise ValueError("不支持的导出格式：%s" % fmt)
    if not resume_text(job) and not _sections(job):
        raise ValueError("该岗位没有可导出的文字简历")
    target_dir = Path(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / (base_filename(job) + FORMAT_EXTENSIONS[fmt])
    if fmt == "docx":
        _write_word(job, path)
    elif fmt == "md":
        _write_markdown(job, path)
    else:
        _write_excel(job, path)
    return path


def export_jobs(jobs: list, folder, fmt: str) -> dict:
    """逐岗位导出；单条失败不阻断其余岗位。"""
    exported, failures = [], []
    for job in jobs or []:
        try:
            exported.append(export_one(job, folder, fmt))
        except Exception as exc:
            failures.append({"job": job.get("title") or "", "error": str(exc)})
            log.warning("导出失败：%s：%s", job.get("title"), exc)
    return {"exported": exported, "failures": failures, "folder": str(folder), "format": fmt}

