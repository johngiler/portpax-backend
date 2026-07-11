from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.models import Booking

ACCENT = HexColor("#3478b5")
TEXT = HexColor("#18181b")
MUTED = HexColor("#71717a")
RULE = HexColor("#e4e4e7")

BRAND_LOGO_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "bookings" / "portpax_isotype.png"
)


def _draw_image(pdf: canvas.Canvas, path: str | Path, x: float, y: float, max_w: float, max_h: float) -> None:
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
    except Exception:
        pass


def build_confirmation_pdf(booking: Booking) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 2 * cm

    # Header band
    header_h = 3.2 * cm
    pdf.setFillColor(HexColor("#f4f8fc"))
    pdf.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    pdf.setStrokeColor(ACCENT)
    pdf.setLineWidth(2.5)
    pdf.line(0, height - header_h, width, height - header_h)

    logo_box = 2.2 * cm
    logo_y = height - header_h + 0.5 * cm

    # Vessel logo (left)
    vessel = booking.vessel
    if vessel.logo:
        _draw_image(
            pdf,
            vessel.logo.path,
            margin,
            logo_y,
            logo_box,
            logo_box,
        )
    else:
        pdf.setFillColor(HexColor("#e8eef5"))
        pdf.roundRect(margin, logo_y, logo_box, logo_box, 6, fill=1, stroke=0)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(margin + logo_box / 2, logo_y + logo_box / 2 - 3, "Barco")

    # ITM / PortPax brand (right)
    if BRAND_LOGO_PATH.is_file():
        _draw_image(
            pdf,
            BRAND_LOGO_PATH,
            width - margin - logo_box,
            logo_y,
            logo_box,
            logo_box,
        )
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(width - margin - logo_box - 0.35 * cm, logo_y + logo_box * 0.55, "ITM Group")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - margin - logo_box - 0.35 * cm, logo_y + logo_box * 0.28, "PortPax")

    # Title
    y = height - header_h - 1.2 * cm
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, y, "Confirmación de escala")
    y -= 0.45 * cm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin, y, "Documento de confirmación operativa")
    y -= 0.9 * cm

    rows = [
        ("Código reserva", booking.booking_code),
        ("Puerto", f"{booking.port.name} ({booking.port.code})"),
        ("Naviera", booking.shipping_line.name),
        ("Barco", booking.vessel.name),
        ("Fecha de escala", booking.call_date.isoformat()),
        ("Posición", booking.position.code if booking.position_id else "Por asignar"),
        ("ETA", booking.eta.strftime("%H:%M") if booking.eta else "—"),
        ("ETD", booking.etd.strftime("%H:%M") if booking.etd else "—"),
        ("Estado", booking.get_status_display()),
    ]

    label_w = 4.2 * cm
    row_h = 0.85 * cm
    for i, (label, value) in enumerate(rows):
        if i % 2 == 0:
            pdf.setFillColor(HexColor("#fafafa"))
            pdf.rect(margin - 0.15 * cm, y - 0.25 * cm, width - 2 * margin + 0.3 * cm, row_h, fill=1, stroke=0)

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margin, y, label)
        pdf.setFillColor(TEXT)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin + label_w, y, str(value))
        y -= row_h

    # Footer
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.5)
    pdf.line(margin, 2.4 * cm, width - margin, 2.4 * cm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 1.8 * cm, "Documento generado por PortPax — ITM Group")
    pdf.drawRightString(width - margin, 1.8 * cm, booking.call_date.isoformat())

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def save_confirmation_pdf(booking: Booking) -> None:
    pdf_bytes = build_confirmation_pdf(booking)
    filename = f"confirmation_{booking.booking_code}.pdf"
    booking.confirmation_pdf.save(filename, ContentFile(pdf_bytes), save=True)
