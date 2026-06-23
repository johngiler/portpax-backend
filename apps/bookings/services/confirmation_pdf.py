from io import BytesIO

from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.models import Booking


def build_confirmation_pdf(booking: Booking) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(2 * cm, y, "Confirmación de escala — PortPax")
    y -= 1.2 * cm

    pdf.setFont("Helvetica", 11)
    lines = [
        f"Folio: {booking.folio or 'Pendiente'}",
        f"Código reserva: {booking.booking_code}",
        f"Puerto: {booking.port.name} ({booking.port.code})",
        f"Naviera: {booking.shipping_line.name}",
        f"Barco: {booking.vessel.name}",
        f"Fecha de escala: {booking.call_date.isoformat()}",
        f"Posición: {booking.position.code if booking.position_id else 'Por asignar'}",
        f"ETA: {booking.eta.strftime('%H:%M') if booking.eta else '—'}",
        f"ETD: {booking.etd.strftime('%H:%M') if booking.etd else '—'}",
        f"PAX planificado: {booking.planned_pax if booking.planned_pax is not None else '—'}",
        f"Estado: {booking.get_status_display()}",
    ]
    for line in lines:
        pdf.drawString(2 * cm, y, line)
        y -= 0.7 * cm

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(2 * cm, 2 * cm, "Documento generado por PortPax — ITM Group")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def save_confirmation_pdf(booking: Booking) -> None:
    pdf_bytes = build_confirmation_pdf(booking)
    filename = f"confirmation_{booking.booking_code}.pdf"
    booking.confirmation_pdf.save(filename, ContentFile(pdf_bytes), save=True)
