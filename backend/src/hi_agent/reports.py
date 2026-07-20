"""Authoritative, in-memory RAG run reports in Markdown, DOCX and PDF."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from docx import Document as WordDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


@dataclass(frozen=True)
class RagReportData:
    run_id: str
    knowledge_base: str
    question: str
    answer: str
    workflow: list[str]
    citations: list[dict[str, Any]]
    generated_at: datetime


def _citation_text(item: dict[str, Any], index: int) -> str:
    page = f"，第 {item['page']} 页" if item.get("page") else ""
    score = f"，相关度 {float(item['score']):.4f}" if item.get("score") is not None else ""
    return f"[{index}] {item.get('filename', '未知文件')}{page}，块 {item.get('chunk_index', '-')}{score}"


def _markdown_text(value: object) -> str:
    """Render untrusted labels without allowing HTML or Markdown structure injection."""

    return (
        str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", " ").replace("\n", " ")
    )


def _markdown_block(value: str) -> str:
    longest = max((len(part) for part in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def render_report(data: RagReportData, output_format: Literal["md", "docx", "pdf"]) -> tuple[bytes, str, str]:
    stamp = data.generated_at.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    base = f"RAG-report-{stamp}"
    if output_format == "md":
        return _markdown(data).encode("utf-8"), f"{base}.md", "text/markdown; charset=utf-8"
    if output_format == "docx":
        return _docx(data), f"{base}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return _pdf(data), f"{base}.pdf", "application/pdf"


def _markdown(data: RagReportData) -> str:
    workflow = (
        "\n".join(f"{index}. {_markdown_text(name)}" for index, name in enumerate(data.workflow, 1)) or "无可用流程事件"
    )
    citations = (
        "\n".join(_markdown_text(_citation_text(item, index)) for index, item in enumerate(data.citations, 1))
        or "未返回引用"
    )
    knowledge_base = _markdown_text(data.knowledge_base)
    return (
        f"# {knowledge_base} · RAG 问答报告\n\n"
        f"- 生成时间：{data.generated_at.astimezone(UTC).isoformat()}\n- Run ID：`{data.run_id}`\n"
        f"- 知识库：{knowledge_base}\n\n## 问题\n\n{_markdown_block(data.question)}\n\n"
        f"## 回答\n\n{_markdown_block(data.answer)}\n\n"
        f"## 执行流程\n\n{workflow}\n\n## 引用来源\n\n{citations}\n"
    )


def _set_font(run: Any, size: float, *, bold: bool = False, color: str = "263238") -> None:
    run.font.name = "Arial"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Noto Sans SC")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _docx(data: RagReportData) -> bytes:
    doc = WordDocument()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(1)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(11)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Noto Sans SC")
    normal.paragraph_format.space_after, normal.paragraph_format.line_spacing = Pt(6), 1.1
    for name, size, color, before, after in (
        ("Heading 1", 16, "2E74B5", 16, 8),
        ("Heading 2", 13, "2E74B5", 12, 6),
        ("Heading 3", 12, "1F4D78", 8, 4),
    ):
        style = styles[name]
        style.font.name, style.font.size, style.font.bold = "Arial", Pt(size), True
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Noto Sans SC")
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before, style.paragraph_format.space_after = Pt(before), Pt(after)
    for name in ("List Number", "List Bullet"):
        styles[name]._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Noto Sans SC")
    header = section.header.paragraphs[0]
    _set_font(header.add_run("HI-AGENT · RAG RUN REPORT"), 8.5, bold=True, color="6B7280")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(footer.add_run(f"Run {data.run_id}"), 8, color="6B7280")

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    _set_font(title.add_run("RAG 问答报告"), 24, bold=True, color="16324F")
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    _set_font(subtitle.add_run(data.knowledge_base), 13, color="4B6478")
    for label, value in (
        ("生成时间", data.generated_at.astimezone(UTC).isoformat()),
        ("Run ID", data.run_id),
        ("知识库", data.knowledge_base),
    ):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        _set_font(paragraph.add_run(f"{label}："), 10, bold=True)
        _set_font(paragraph.add_run(value), 10)

    for heading, content in (("问题", data.question), ("回答", data.answer)):
        doc.add_heading(heading, level=1)
        for line in content.splitlines() or [""]:
            paragraph = doc.add_paragraph(line)
            paragraph.paragraph_format.keep_together = True
    doc.add_heading("执行流程", level=1)
    for name in data.workflow or ["无可用流程事件"]:
        doc.add_paragraph(name, style="List Number")
    doc.add_heading("引用来源", level=1)
    for index, item in enumerate(data.citations, 1):
        doc.add_paragraph(_citation_text(item, index))
    if not data.citations:
        doc.add_paragraph("未返回引用")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


_PDF_FONT = "NotoSansSC"


def _pdf_font_path() -> Path:
    path = Path(__file__).with_name("assets") / "NotoSansSC-Regular.ttf"
    if not path.is_file():
        raise RuntimeError("PDF 中文字体资源缺失")
    return path


def _pdf(data: RagReportData) -> bytes:
    if _PDF_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_PDF_FONT, str(_pdf_font_path())))
    output = BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CNBody", parent=styles["BodyText"], fontName=_PDF_FONT, fontSize=10.5, leading=16, spaceAfter=7
    )
    heading = ParagraphStyle(
        "CNHeading", parent=body, fontSize=16, leading=22, textColor=HexColor("#2E74B5"), spaceBefore=14, spaceAfter=7
    )
    title = ParagraphStyle(
        "CNTitle",
        parent=body,
        fontSize=24,
        leading=30,
        textColor=HexColor("#16324F"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    meta = ParagraphStyle(
        "CNMeta", parent=body, fontSize=8.5, leading=13, textColor=HexColor("#607D8B"), alignment=TA_CENTER
    )

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(_PDF_FONT, 8)
        canvas.setFillColor(HexColor("#78909C"))
        canvas.drawString(20 * mm, 12 * mm, f"Hi-agent · Run {data.run_id}")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="RAG 问答报告",
        author="Hi-agent",
    )
    story: list[Any] = [
        Paragraph("RAG 问答报告", title),
        Paragraph(html.escape(data.knowledge_base), meta),
        Spacer(1, 8 * mm),
    ]
    metadata = (
        f"生成时间：{data.generated_at.astimezone(UTC).isoformat()}<br/>"
        f"Run ID：{html.escape(data.run_id)}<br/>"
        f"知识库：{html.escape(data.knowledge_base)}"
    )
    story.extend([Paragraph(metadata, meta), Spacer(1, 5 * mm)])
    for label, content in (("问题", data.question), ("回答", data.answer)):
        story.append(Paragraph(label, heading))
        for line in content.splitlines() or [""]:
            story.append(Paragraph(html.escape(line) or "&nbsp;", body))
    story.append(Paragraph("执行流程", heading))
    story.append(
        ListFlowable(
            [ListItem(Paragraph(html.escape(name), body)) for name in data.workflow or ["无可用流程事件"]],
            bulletType="1",
            start="1",
        )
    )
    story.append(Paragraph("引用来源", heading))
    citations = [_citation_text(item, index) for index, item in enumerate(data.citations, 1)] or ["未返回引用"]
    story.extend(Paragraph(html.escape(value), body) for value in citations)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
