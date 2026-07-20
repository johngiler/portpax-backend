"""
Booking confirmation PDF.

Uses the shared executive layout in `pdf_layout` (template for other PortPax PDFs).
Header left logo: port logo (not vessel / shipping line).
"""

from io import BytesIO
from typing import Any

from django.core.files.base import ContentFile
from django.db.models import Q, QuerySet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.pdf_layout import (
    ACCENT,
    ACCENT_SOFT,
    LOGO_SIZE,
    MUTED,
    PAGE_MARGIN,
    RULE,
    TEXT,
    draw_brand_header_right,
    draw_footer,
    draw_logo_slot,
    draw_metric_card,
    draw_section_title,
    draw_top_accent_bar,
)
from apps.catalogs.utils.position_code import position_short_code

# Statuses that get a confirmation slip (M10: CO or CL).
CONFIRMATION_PDF_STATUSES = (BookingStatus.CO, BookingStatus.CL)


def build_confirmation_pdf(booking: Booking) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = PAGE_MARGIN
    content_w = width - 2 * margin

    draw_top_accent_bar(pdf, width, height)

    logo_size = LOGO_SIZE
    logo_y = height - 3.1 * cm
    port = booking.port
    port_logo = port.logo.path if port.logo else None
    draw_logo_slot(pdf, margin, logo_y, logo_size, port_logo, "Puerto")
    draw_brand_header_right(pdf, width, margin, logo_y, logo_size)

    y = logo_y - 1.15 * cm
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(margin, y, "Confirmación de escala")
    y -= 0.55 * cm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, "Confirmación operativa · uso interno y naviera")

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

    y -= 1.0 * cm
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, y, "CÓDIGO DE RESERVA")
    y -= 0.4 * cm
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin, y, booking.booking_code)

    y -= 0.9 * cm
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.7)
    pdf.line(margin, y, width - margin, y)
    y -= 0.55 * cm
    draw_section_title(pdf, margin, y, "PARTES")
    y -= 0.85 * cm

    card_h = 1.55 * cm
    gap = 0.35 * cm
    card_w = (content_w - gap) / 2
    draw_metric_card(
        pdf,
        margin,
        y - card_h + 0.35 * cm,
        card_w,
        card_h,
        "Naviera",
        booking.shipping_line.name,
    )
    draw_metric_card(
        pdf,
        margin + card_w + gap,
        y - card_h + 0.35 * cm,
        card_w,
        card_h,
        "Barco",
        booking.vessel.name,
    )
    y -= card_h + 0.55 * cm

    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.7)
    pdf.line(margin, y, width - margin, y)
    y -= 0.55 * cm
    draw_section_title(pdf, margin, y, "DETALLE DE ESCALA")
    y -= 0.85 * cm

    port_label = port.commercial_name or port.name
    if booking.position_id and booking.position:
        berth_label = position_short_code(port.code, booking.position.code)
    else:
        berth_label = "Por asignar"
    eta = booking.eta.strftime("%H:%M") if booking.eta else "—"
    etd = booking.etd.strftime("%H:%M") if booking.etd else "—"
    planned_pax = (
        f"{booking.planned_pax:,}".replace(",", ".")
        if booking.planned_pax is not None
        else "—"
    )

    row1_y = y - card_h + 0.35 * cm
    draw_metric_card(pdf, margin, row1_y, card_w, card_h, "Puerto", port_label)
    draw_metric_card(
        pdf,
        margin + card_w + gap,
        row1_y,
        card_w,
        card_h,
        "Muelle",
        berth_label,
    )
    y -= card_h + 0.35 * cm

    row2_y = y - card_h + 0.35 * cm
    draw_metric_card(pdf, margin, row2_y, card_w, card_h, "ETA", eta)
    draw_metric_card(
        pdf,
        margin + card_w + gap,
        row2_y,
        card_w,
        card_h,
        "ETD",
        etd,
    )
    y -= card_h + 0.35 * cm

    row3_y = y - card_h + 0.35 * cm
    draw_metric_card(
        pdf,
        margin,
        row3_y,
        card_w,
        card_h,
        "PAX proyectados",
        planned_pax,
    )

    draw_footer(pdf, width, margin)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def save_confirmation_pdf(booking: Booking) -> None:
    pdf_bytes = build_confirmation_pdf(booking)
    filename = f"confirmation_{booking.booking_code}.pdf"
    booking.confirmation_pdf.save(filename, ContentFile(pdf_bytes), save=True)


def generate_confirmation_pdfs(
    *,
    only_missing: bool = True,
    queryset: QuerySet[Booking] | None = None,
) -> dict[str, Any]:
    """
    Generate confirmation PDFs for CO/CL bookings.

    By default only rows without a stored file (for post-import backfill).
    Pass only_missing=False to regenerate all.
    """
    qs = queryset if queryset is not None else Booking.objects.filter(
        status__in=CONFIRMATION_PDF_STATUSES,
    )
    qs = qs.filter(status__in=CONFIRMATION_PDF_STATUSES).select_related(
        "port",
        "shipping_line",
        "vessel",
        "position",
    )
    if only_missing:
        qs = qs.filter(Q(confirmation_pdf="") | Q(confirmation_pdf__isnull=True))

    generated = 0
    errors: list[dict[str, Any]] = []
    for booking in qs.iterator(chunk_size=50):
        try:
            save_confirmation_pdf(booking)
            generated += 1
        except Exception as exc:  # noqa: BLE001 — continue batch; report failures
            errors.append(
                {
                    "id": booking.id,
                    "booking_code": booking.booking_code,
                    "error": str(exc),
                }
            )

    return {
        "generated": generated,
        "error_count": len(errors),
        "errors": errors[:100],
    }
