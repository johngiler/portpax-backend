"""
Executive PDF layout primitives for PortPax documents.

This module is the visual template for future booking/ops PDFs
(confirmation, reports, etc.). Keep new documents consistent with these
helpers and colors rather than inventing a parallel style.
"""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

ACCENT = HexColor("#3478b5")
ACCENT_SOFT = HexColor("#e8f1f8")
TEXT = HexColor("#18181b")
MUTED = HexColor("#71717a")
RULE = HexColor("#e4e4e7")
CARD_BG = HexColor("#fafafa")
WHITE = HexColor("#ffffff")

BRAND_LOGO_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "bookings" / "portpax_isotype.png"
)

PAGE_MARGIN = 1.8 * cm
LOGO_SIZE = 2.4 * cm


def draw_image(
    pdf: canvas.Canvas,
    path: str | Path,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
) -> bool:
    try:
        pdf.drawImage(
            str(path),
            x,
            y,
            width=max_w,
            height=max_h,
            preserveAspectRatio=True,
            mask="auto",
            anchor="c",
        )
        return True
    except Exception:
        return False


def draw_logo_slot(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    size: float,
    image_path: str | Path | None,
    fallback: str,
) -> None:
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, y, size, size, 8, fill=1, stroke=1)
    inset = 0.28 * cm
    if image_path and draw_image(
        pdf, image_path, x + inset, y + inset, size - 2 * inset, size - 2 * inset
    ):
        return
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(x + size / 2, y + size / 2 - 3, fallback)


def draw_metric_card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    value: str,
) -> None:
    pdf.setFillColor(CARD_BG)
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.6)
    pdf.roundRect(x, y, w, h, 6, fill=1, stroke=1)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(x + 0.4 * cm, y + h - 0.55 * cm, label.upper())
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 11)
    max_chars = max(18, int((w - 0.8 * cm) / 6.2))
    display = value if len(value) <= max_chars else value[: max_chars - 1] + "…"
    pdf.drawString(x + 0.4 * cm, y + 0.45 * cm, display)


def draw_top_accent_bar(pdf: canvas.Canvas, page_width: float, page_height: float) -> None:
    pdf.setFillColor(ACCENT)
    pdf.rect(0, page_height - 0.35 * cm, page_width, 0.35 * cm, fill=1, stroke=0)


def draw_brand_header_right(
    pdf: canvas.Canvas,
    page_width: float,
    margin: float,
    logo_y: float,
    logo_size: float = LOGO_SIZE,
) -> None:
    brand_x = page_width - margin - logo_size
    brand_path = BRAND_LOGO_PATH if BRAND_LOGO_PATH.is_file() else None
    draw_logo_slot(pdf, brand_x, logo_y, logo_size, brand_path, "ITM")
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(brand_x - 0.35 * cm, logo_y + logo_size * 0.58, "ITM Group")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(brand_x - 0.35 * cm, logo_y + logo_size * 0.32, "PortPax")


def draw_section_title(pdf: canvas.Canvas, x: float, y: float, title: str) -> None:
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x, y, title)


def draw_footer(
    pdf: canvas.Canvas,
    page_width: float,
    margin: float,
    left: str = "Generado por PortPax · ITM Group",
    right: str = "Documento confidencial",
) -> None:
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 2.3 * cm, page_width - margin, 2.3 * cm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 1.7 * cm, left)
    pdf.drawRightString(page_width - margin, 1.7 * cm, right)
