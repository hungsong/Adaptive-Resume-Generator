# -*- coding: utf-8 -*-
"""旧简历文件读取：txt / md / docx / pdf -> 纯文本（供「一键粘贴分析」使用）。"""
from __future__ import annotations

from pathlib import Path

from core.applog import get_logger

log = get_logger("readers")

TEXT_SUFFIXES = (".txt", ".md", ".markdown")
ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030")


def _read_text_file(path: Path) -> str:
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise RuntimeError("读取文件失败：%s" % exc) from exc
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("未安装 python-docx，无法读取 Word 文件") from exc
    doc = Document(str(path))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("未安装 pypdf，无法读取 PDF 文件") from exc
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            log.warning("PDF 某页解析失败，已跳过")
    return "\n".join(parts)


def read_document_text(path) -> str:
    p = Path(path)
    if not p.exists():
        raise RuntimeError("文件不存在：%s" % p)
    suffix = p.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = _read_text_file(p)
    elif suffix == ".docx":
        text = _read_docx(p)
    elif suffix == ".pdf":
        text = _read_pdf(p)
    elif suffix == ".doc":
        raise RuntimeError("不支持旧版 .doc，请另存为 .docx 后再导入")
    else:
        raise RuntimeError("不支持的文件类型：%s" % suffix)
    text = text.strip()
    if not text:
        raise RuntimeError("文件里没有读到文字（如果是扫描件 PDF，需要先做 OCR）")
    return text
