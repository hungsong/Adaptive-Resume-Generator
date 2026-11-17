# -*- coding: utf-8 -*-
"""渲染与导出：简历文档 -> HTML / Markdown / PDF。

预览与导出共用同一份 HTML（单一渲染源，避免两套排版分叉）。
HTML 全部使用行内样式，保证 Qt 的富文本引擎（QTextBrowser / QTextDocument）能正确显示。
"""
from __future__ import annotations

import html as _html
from pathlib import Path

ACCENT = "#1a4b8c"
MUTED = "#666666"


def esc(text) -> str:
    return _html.escape(str(text or ""), quote=False)


def _contact_line(header: dict) -> str:
    parts = [
        header.get("phone"),
        header.get("email"),
        header.get("city"),
        header.get("target"),
    ]
    links = str(header.get("links") or "").replace("\n", " / ").strip()
    if links:
        parts.append(links)
    return " &nbsp;|&nbsp; ".join(esc(p) for p in parts if p)


def _bullet_html(b: dict, show_flags: bool) -> str:
    text = b.get("text") if isinstance(b, dict) else str(b)
    flagged = bool(isinstance(b, dict) and b.get("flagged"))
    if flagged and show_flags:
        return '<li style="color:#b00020;">%s<span style="color:#b00020;">【待核实】</span></li>' % esc(text)
    return "<li>%s</li>" % esc(text)


def build_html(doc: dict, show_flags: bool = True) -> str:
    header = doc.get("header") or {}
    out = []
    out.append(
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family:\'Microsoft YaHei UI\',\'Microsoft YaHei\',sans-serif;'
        "font-size:10.5pt;color:#1a1a1a;line-height:170%;\">"
    )
    out.append('<p style="font-size:19pt;font-weight:bold;margin:0 0 2px 0;">%s</p>' % esc(header.get("name")))
    contact = _contact_line(header)
    if contact:
        out.append('<p style="font-size:9.5pt;color:%s;margin:0 0 6px 0;">%s</p>' % (MUTED, contact))

    summary = str(doc.get("summary") or "").strip()
    if summary:
        out.append(
            '<p style="font-size:12pt;font-weight:bold;color:%s;margin:10px 0 4px 0;">▍ 个人简介</p>' % ACCENT
        )
        color = "#b00020" if (show_flags and doc.get("summary_flagged")) else "#1a1a1a"
        out.append('<p style="margin:0;color:%s;">%s</p>' % (color, esc(summary)))

    for sec in doc.get("sections") or []:
        items = sec.get("items") or []
        if not items:
            continue
        out.append(
            '<p style="font-size:12pt;font-weight:bold;color:%s;margin:12px 0 4px 0;">▍ %s</p>'
            % (ACCENT, esc(sec.get("title") or ""))
        )
        key = sec.get("key")
        if key == "skills":
            chips = []
            for item in items:
                text = item.get("text") if isinstance(item, dict) else item
                chips.append(esc(text))
            out.append('<p style="margin:0;">%s</p>' % " &nbsp;·&nbsp; ".join(c for c in chips if c))
            continue
        if key in ("certificates", "achievements"):
            out.append("<ul style=\"margin:0;padding-left:18px;\">")
            for item in items:
                out.append(_bullet_html(item, show_flags))
            out.append("</ul>")
            continue
        for item in items:
            org = esc(item.get("org"))
            role = esc(item.get("role"))
            start = esc(item.get("start"))
            end = esc(item.get("end"))
            period = "-".join([p for p in (start, end) if p and p != "-"])
            role_html = ('<span style="color:#333333;">%s</span>' % role) if role else ""
            out.append(
                '<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px;">'
                "<tr>"
                '<td style="font-weight:bold;">{org} &nbsp; {role}</td>'
                '<td align="right" style="color:{muted};font-size:9.5pt;">{period}</td>'
                "</tr></table>".format(org=org, role=role_html, muted=MUTED, period=period)
            )
            bullets = item.get("bullets") or []
            if bullets:
                out.append('<ul style="margin:2px 0 0 0;padding-left:18px;">')
                for b in bullets:
                    out.append(_bullet_html(b, show_flags))
                out.append("</ul>")
    out.append("</body></html>")
    return "".join(out)


def build_markdown(doc: dict) -> str:
    header = doc.get("header") or {}
    lines = ["# %s" % (header.get("name") or "个人简历"), ""]
    contact = _contact_line(header).replace(" &nbsp;|&nbsp; ", " | ").replace("&nbsp;", " ")
    if contact:
        lines += [contact, ""]
    summary = str(doc.get("summary") or "").strip()
    if summary:
        lines += ["## 个人简介", "", summary, ""]
    for sec in doc.get("sections") or []:
        items = sec.get("items") or []
        if not items:
            continue
        lines += ["## %s" % (sec.get("title") or ""), ""]
        key = sec.get("key")
        if key == "skills":
            lines.append(" · ".join(str(i.get("text") if isinstance(i, dict) else i) for i in items))
            lines.append("")
            continue
        if key in ("certificates", "achievements"):
            for item in items:
                text = item.get("text") if isinstance(item, dict) else item
                lines.append("- %s" % text)
            lines.append("")
            continue
        for item in items:
            org = item.get("org") or ""
            role = item.get("role") or ""
            period = " - ".join([p for p in (item.get("start"), item.get("end")) if p])
            head = " ".join([p for p in (org, role) if p])
            lines.append("### %s%s" % (head, ("  |  " + period) if period else ""))
            for b in item.get("bullets") or []:
                text = b.get("text") if isinstance(b, dict) else b
                lines.append("- %s" % text)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def export_markdown(doc: dict, path) -> str:
    path = Path(path)
    path.write_text(build_markdown(doc), encoding="utf-8")
    return str(path)


def export_pdf(html_text: str, path, margin_mm=(18.0, 16.0, 18.0, 16.0)) -> str:
    """用 Qt 原生打印链路把 HTML 渲染成 A4 PDF（离线、无需浏览器）。"""
    from PyQt5.QtCore import QSizeF
    from PyQt5.QtGui import QFont, QTextDocument
    from PyQt5.QtPrintSupport import QPrinter

    path = Path(path)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPrinter.A4)
    left, top, right, bottom = margin_mm
    printer.setPageMargins(left, top, right, bottom, QPrinter.Millimeter)

    doc = QTextDocument()
    doc.setDefaultFont(QFont("Microsoft YaHei UI", 10))
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(printer.pageRect().width(), printer.pageRect().height()))
    doc.setHtml(html_text)
    doc.print_(printer)
    return str(path)
