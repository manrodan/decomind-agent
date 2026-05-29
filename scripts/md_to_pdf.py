"""
Convierte cualquier .md del repo a un PDF legible (reportlab).
Sin dependencias extra — solo reportlab que ya está en el proyecto.

Uso:
    python -m scripts.md_to_pdf docs/system-overview.md
    python -m scripts.md_to_pdf docs/system-overview.md outputs/overview.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle, Preformatted,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "outputs"


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("H1", parent=ss["Heading1"], fontSize=18, leading=22,
                             textColor=colors.HexColor("#1F6FEB"),
                             spaceBefore=14, spaceAfter=10),
        "h2": ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, leading=18,
                             textColor=colors.HexColor("#1F6FEB"),
                             spaceBefore=10, spaceAfter=6),
        "h3": ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11, leading=14,
                             textColor=colors.HexColor("#333333"),
                             spaceBefore=6, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=ss["BodyText"], fontSize=9.5,
                               leading=13, alignment=TA_LEFT,
                               textColor=colors.HexColor("#1f2937")),
        "quote": ParagraphStyle("Quote", parent=ss["BodyText"], fontSize=9.5,
                                leading=13, textColor=colors.HexColor("#6b7280"),
                                leftIndent=12, borderColor=colors.HexColor("#1F6FEB"),
                                borderWidth=0, borderPadding=6),
        "code_block": ParagraphStyle("Code", parent=ss["Code"], fontSize=8,
                                     leading=10,
                                     textColor=colors.HexColor("#111827"),
                                     backColor=colors.HexColor("#F3F4F6")),
    }


def _inline(text: str) -> str:
    """Markdown inline → mini HTML (bold, italic, code, links)."""
    # escape básico
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`",
                  r'<font face="Courier" color="#7c3aed">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  r'<link href="\2" color="#1F6FEB">\1</link>', text)
    return text


def md_to_flowables(md: str, S: dict) -> list:
    """Parser markdown muy simple: h1/h2/h3, code blocks, tablas, bullets,
    blockquotes, párrafos. No es 100% spec — suficiente para nuestros docs.
    """
    flow = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # === code block ===
        if line.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # cerrar ```
            code_text = "\n".join(code_lines)
            flow.append(Preformatted(code_text, S["code_block"]))
            flow.append(Spacer(1, 4))
            continue

        # === header ===
        if line.startswith("# "):
            flow.append(Paragraph(_inline(line[2:].strip()), S["h1"]))
            i += 1; continue
        if line.startswith("## "):
            flow.append(Paragraph(_inline(line[3:].strip()), S["h2"]))
            i += 1; continue
        if line.startswith("### "):
            flow.append(Paragraph(_inline(line[4:].strip()), S["h3"]))
            i += 1; continue

        # === blockquote ===
        if line.startswith("> "):
            qlines = []
            while i < len(lines) and lines[i].startswith(">"):
                qlines.append(lines[i].lstrip("> ").rstrip())
                i += 1
            quote = " ".join(qlines)
            flow.append(Paragraph(_inline(quote), S["quote"]))
            flow.append(Spacer(1, 4))
            continue

        # === tabla ===
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|", lines[i+1]):
            header = [c.strip() for c in line.strip("|").split("|")]
            i += 2  # saltar separator
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                rows.append(cells)
                i += 1
            # construir tabla
            data = [[Paragraph(_inline(c), S["body"]) for c in header]]
            for r in rows:
                # Normalizar nº de columnas
                while len(r) < len(header):
                    r.append("")
                data.append([Paragraph(_inline(c), S["body"]) for c in r[:len(header)]])
            t = Table(data, repeatRows=1,
                      colWidths=[(170 / len(header)) * mm] * len(header))
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F6FEB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F4F6FA")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 6))
            continue

        # === bullet / numbered list ===
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < len(lines) and (
                re.match(r"^\s*[-*]\s+", lines[i]) or
                re.match(r"^\s*\d+\.\s+", lines[i])
            ):
                txt = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", lines[i])
                items.append(_inline(txt))
                i += 1
            for txt in items:
                flow.append(Paragraph(f"&nbsp;&nbsp;• {txt}", S["body"]))
            flow.append(Spacer(1, 4))
            continue

        # === horizontal rule ===
        if re.match(r"^\s*---+\s*$", line):
            flow.append(Spacer(1, 6))
            flow.append(Table([[""]], colWidths=[170 * mm], rowHeights=[1],
                              style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5,
                                                 colors.HexColor("#CCCCCC"))])))
            flow.append(Spacer(1, 6))
            i += 1; continue

        # === línea vacía ===
        if not line.strip():
            flow.append(Spacer(1, 4))
            i += 1; continue

        # === párrafo normal ===
        flow.append(Paragraph(_inline(line), S["body"]))
        i += 1

    return flow


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.md_to_pdf <input.md> [output.pdf]")
        sys.exit(1)
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"No existe: {src}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        dst = Path(sys.argv[2])
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        dst = OUTPUT_DIR / (src.stem + ".pdf")

    md = src.read_text(encoding="utf-8")
    S = _styles()
    flow = md_to_flowables(md, S)

    doc = SimpleDocTemplate(
        str(dst), pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=src.stem, author="Decomind Agent",
    )
    doc.build(flow)
    print(f"OK: {dst}  ({dst.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
