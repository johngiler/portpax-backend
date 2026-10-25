"""Shared header/footer chrome for arrivals flyers."""

from __future__ import annotations

from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from apps.bookings.services.arrivals_pdf.labels import (
    FOOTER_NOTE_CAL,
    FOOTER_NOTE_LIST,
    updated_label,
)

NAVY = HexColor("#1F4E79")
NAVY_DEEP = HexColor("#163556")
STEEL = HexColor("#5B9BD5")
INK = HexColor("#111111")
MUTED = HexColor("#4B5563")
GRID = HexColor("#1A1A1A")

MARGIN = 1.0 * cm
LOGO_MAX_H = 1.7 * cm
LOGO_MAX_W = 3.2 * cm
HEADER_H = 2.15 * cm
FOOTER_BAR_H = 14.0


def draw_logo(
    pdf: canvas.Canvas,
    reader: ImageReader | None,
    x: float,
    y: float,
    max_w: float = LOGO_MAX_W,
    max_h: float = LOGO_MAX_H,
) -> float:
    """Draw logo bottom-left at (x, y). Returns used width."""
    if reader is None:
        return 0
    try:
        iw, ih = reader.getSize()
        if not iw or not ih:
            return 0
        scale = min(max_w / float(iw), max_h / float(ih))
        width, height = float(iw) * scale, float(ih) * scale
        pdf.drawImage(
            reader,
            x,
            y,
            width=width,
            height=height,
            mask="auto",
            preserveAspectRatio=True,
            anchor="sw",
        )
        return width
    except Exception:
        return 0


def draw_filled_diamond(pdf: canvas.Canvas, x: float, y: float, size: float = 4.2) -> None:
    pdf.setFillColor(INK)
    path = pdf.beginPath()
    path.moveTo(x, y + size / 2)
    path.lineTo(x + size / 2, y)
    path.lineTo(x, y - size / 2)
    path.lineTo(x - size / 2, y)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)


def wrap_text_lines(
    pdf: canvas.Canvas,
    text: str,
    max_width: float,
    *,
    font_name: str,
    font_size: float,
    max_lines: int = 3,
) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    pdf.setFont(font_name, font_size)
    if pdf.stringWidth(text) <= max_width:
        return [text]
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if pdf.stringWidth(trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = fit_text(pdf, kept[-1], max_width)
    return kept


def draw_flyer_header(
    pdf: canvas.Canvas,
    page_width: float,
    page_height: float,
    *,
    logo: ImageReader | None,
    title: str,
    subtitle: str = "",
    kicker: str = "",
    total: int | None = None,
    margin: float = MARGIN,
    logo_h: float = LOGO_MAX_H,
    logo_w: float = LOGO_MAX_W,
    title_size: float = 22,
) -> None:
    logo_used = draw_logo(
        pdf, logo, margin, page_height - margin - logo_h, max_w=logo_w, max_h=logo_h
    )
    right_reserve = 2.55 * cm if total is not None else 0.12 * cm
    safe_left = margin + (logo_used + 0.22 * cm if logo_used else 0)
    safe_right = page_width - margin - right_reserve
    safe_w = max(4.4 * cm, safe_right - safe_left)
    cx = safe_left + safe_w / 2

    title_lines = wrap_text_lines(
        pdf, title, safe_w, font_name="Times-Bold", font_size=title_size, max_lines=2
    )
    kicker_size = min(12, title_size - 2) if title_size > 11 else title_size
    kicker_lines = wrap_text_lines(
        pdf, kicker, safe_w, font_name="Times-Bold", font_size=kicker_size, max_lines=2
    )
    y = page_height - margin - 0.5 * cm
    pdf.setFillColor(INK)
    pdf.setFont("Times-Bold", title_size)
    for line in title_lines:
        pdf.drawCentredString(cx, y, line)
        y -= title_size * 1.08
    if kicker_lines:
        y -= 1
        pdf.setFont("Times-Bold", kicker_size)
        for line in kicker_lines:
            pdf.drawCentredString(cx, y, line)
            y -= kicker_size + 2
    if subtitle:
        y -= 2
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 9)
        pdf.drawCentredString(cx, y, fit_text(pdf, subtitle, safe_w))

    if total is not None:
        pdf.setFillColor(NAVY_DEEP)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawRightString(
            page_width - margin, page_height - margin - 0.48 * cm, "TOTAL ARRIBOS"
        )
        pdf.setFont("Times-Bold", 18)
        pdf.drawRightString(
            page_width - margin, page_height - margin - 1.12 * cm, str(total)
        )


def draw_table_footer_bar(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    *,
    updated,
    kind: str = "list",
    page_no: int | None = None,
    page_count: int | None = None,
    height: float = FOOTER_BAR_H,
) -> None:
    """Navy spanning row used as the last row of lista / calendario tables."""
    note_prefix = FOOTER_NOTE_LIST if kind == "list" else FOOTER_NOTE_CAL
    note = f"{note_prefix} {updated_label(updated)}"
    pdf.setFillColor(NAVY_DEEP)
    pdf.rect(x, y, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.7)
    pdf.rect(x, y, width, height, fill=0, stroke=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(x + width / 2, y + 4.0, note)
    if page_no is not None and page_count is not None and page_count > 1:
        pdf.drawRightString(x + width - 6, y + 4.0, f"{page_no} / {page_count}")


def fit_text(pdf: canvas.Canvas, text: str, max_width: float) -> str:
    if max_width <= 0 or pdf.stringWidth(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and pdf.stringWidth(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis


def port_subtitle(port) -> str:
    if port is None:
        return ""
    name = (getattr(port, "name", None) or "").strip()
    commercial = (getattr(port, "commercial_name", None) or "").strip()
    if commercial and commercial != name:
        return commercial
    return name
