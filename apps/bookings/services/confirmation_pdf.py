from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.models import Booking

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


def _draw_image(
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


def _draw_logo_slot(
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
    if image_path and _draw_image(pdf, image_path, x + inset, y + inset, size - 2 * inset, size - 2 * inset):
        return
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(x + size / 2, y + size / 2 - 3, fallback)


def _draw_metric_card(
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
    # Truncate long values visually by clipping to card width
    max_chars = max(18, int((w - 0.8 * cm) / 6.2))
    display = value if len(value) <= max_chars else value[: max_chars - 1] + "…"
    pdf.drawString(x + 0.4 * cm, y + 0.45 * cm, display)


def build_confirmation_pdf(booking: Booking) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 1.8 * cm
    content_w = width - 2 * margin

    # Top accent bar
    pdf.setFillColor(ACCENT)
    pdf.rect(0, height - 0.35 * cm, width, 0.35 * cm, fill=1, stroke=0)

    # Header logos
    logo_size = 2.4 * cm
    logo_y = height - 3.1 * cm
    line = booking.shipping_line
    line_logo = line.logo.path if line.logo else None
    _draw_logo_slot(pdf, margin, logo_y, logo_size, line_logo, "Naviera")

    brand_x = width - margin - logo_size
    brand_path = BRAND_LOGO_PATH if BRAND_LOGO_PATH.is_file() else None
    _draw_logo_slot(pdf, brand_x, logo_y, logo_size, brand_path, "ITM")
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(brand_x - 0.35 * cm, logo_y + logo_size * 0.58, "ITM Group")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(brand_x - 0.35 * cm, logo_y + logo_size * 0.32, "PortPax")

    # Title block
    y = logo_y - 1.15 * cm
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(margin, y, "Confirmación de escala")
    y -= 0.55 * cm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, "Confirmación operativa · uso interno y naviera")

    # Highlight strip: date + status
    y -= 1.15 * cm
    strip_h = 1.55 * cm
    pdf.setFillColor(ACCENT_SOFT)
    pdf.roundRect(margin, y - 0.15 * cm, content_w, strip_h, 8, fill=1, stroke=0)
    pdf.setFillColor(ACCENT)
    pdf.rect(margin, y - 0.15 * cm, 0.18 * cm, strip_h, fill=1, stroke=0)

    call_date = booking.call_date.strftime("%d %b %Y")
    status = booking.get_status_display()
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin + 0.55 * cm, y + strip_h - 0.7 * cm, "FECHA DE ESCALA")
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin + 0.55 * cm, y + 0.35 * cm, call_date)

    mid_x = margin + content_w * 0.48
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(mid_x, y + strip_h - 0.7 * cm, "ESTADO")
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(mid_x, y + 0.35 * cm, status)

    # Booking code reference
    y -= 1.0 * cm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, y, "CÓDIGO DE RESERVA")
    y -= 0.4 * cm
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin, y, booking.booking_code)

    # Section: parties
    y -= 0.9 * cm
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.7)
    pdf.line(margin, y, width - margin, y)
    y -= 0.55 * cm
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin, y, "PARTES")
    y -= 0.85 * cm

    card_h = 1.55 * cm
    gap = 0.35 * cm
    card_w = (content_w - gap) / 2
    _draw_metric_card(pdf, margin, y - card_h + 0.35 * cm, card_w, card_h, "Naviera", line.name)
    _draw_metric_card(
        pdf,
        margin + card_w + gap,
        y - card_h + 0.35 * cm,
        card_w,
        card_h,
        "Barco",
        booking.vessel.name,
    )
    y -= card_h + 0.55 * cm

    # Section: call details
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.7)
    pdf.line(margin, y, width - margin, y)
    y -= 0.55 * cm
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin, y, "DETALLE DE ESCALA")
    y -= 0.85 * cm

    port_label = booking.port.commercial_name or booking.port.name
    position = booking.position.code if booking.position_id else "Por asignar"
    eta = booking.eta.strftime("%H:%M") if booking.eta else "—"
    etd = booking.etd.strftime("%H:%M") if booking.etd else "—"

    row1_y = y - card_h + 0.35 * cm
    _draw_metric_card(pdf, margin, row1_y, card_w, card_h, "Puerto", port_label)
    _draw_metric_card(
        pdf,
        margin + card_w + gap,
        row1_y,
        card_w,
        card_h,
        "Posición",
        position,
    )
    y -= card_h + 0.35 * cm

    row2_y = y - card_h + 0.35 * cm
    _draw_metric_card(pdf, margin, row2_y, card_w, card_h, "ETA", eta)
    _draw_metric_card(
        pdf,
        margin + card_w + gap,
        row2_y,
        card_w,
        card_h,
        "ETD",
        etd,
    )

    # Footer
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 2.3 * cm, width - margin, 2.3 * cm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 1.7 * cm, "Generado por PortPax · ITM Group")
    pdf.drawRightString(width - margin, 1.7 * cm, "Documento confidencial")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def save_confirmation_pdf(booking: Booking) -> None:
    pdf_bytes = build_confirmation_pdf(booking)
    filename = f"confirmation_{booking.booking_code}.pdf"
    booking.confirmation_pdf.save(filename, ContentFile(pdf_bytes), save=True)
