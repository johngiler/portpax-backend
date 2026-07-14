"""Export bookings list to Excel (.xlsx) or CSV."""

from __future__ import annotations

import csv
from datetime import date, datetime
from io import BytesIO, StringIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.bookings.models import Booking, BookingStatus

HEADERS = [
    "Código",
    "Estado",
    "Puerto",
    "Naviera",
    "Barco",
    "Posición",
    "Fecha de escala",
    "ETA",
    "ETD",
    "PAX planificado",
    "PAX real",
    "Tripulación real",
    "Motivo de cancelación",
    "Notas",
    "Creado",
    "Actualizado",
]

STATUS_LABELS_ES = {
    BookingStatus.REQUESTED: "Solicitada",
    BookingStatus.CONFIRMED: "Confirmada",
    BookingStatus.CANCELLED: "Cancelada",
}


def _status_label(booking: Booking, today: date) -> str:
    if booking.status == BookingStatus.CANCELLED:
        return STATUS_LABELS_ES[BookingStatus.CANCELLED]
    if booking.call_date < today and booking.status in (
        BookingStatus.REQUESTED,
        BookingStatus.CONFIRMED,
    ):
        return "Completada"
    return STATUS_LABELS_ES.get(booking.status, booking.get_status_display())


def _format_time(value) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def _format_datetime(value: datetime) -> str:
    local = timezone.localtime(value)
    return local.strftime("%d/%m/%Y %H:%M")


def _cell_value(value) -> str | int:
    if value is None:
        return ""
    return value


def booking_export_row(booking: Booking, today: date | None = None) -> list:
    today = today or timezone.localdate()
    return [
        booking.booking_code,
        _status_label(booking, today),
        booking.port.name,
        booking.shipping_line.name,
        booking.vessel.name,
        booking.position.code if booking.position_id else "",
        booking.call_date.isoformat(),
        _format_time(booking.eta),
        _format_time(booking.etd),
        _cell_value(booking.planned_pax),
        _cell_value(booking.actual_pax),
        _cell_value(booking.actual_crew),
        booking.get_cancellation_reason_display() if booking.cancellation_reason else "",
        booking.notes or "",
        _format_datetime(booking.created_at),
        _format_datetime(booking.updated_at),
    ]


def build_bookings_xlsx(bookings) -> bytes:
    today = timezone.localdate()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reservas"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for booking in bookings:
        sheet.append(booking_export_row(booking, today))
    for column_cells in sheet.columns:
        max_len = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        sheet.column_dimensions[column_letter].width = min(max_len + 2, 40)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_bookings_csv(bookings) -> bytes:
    today = timezone.localdate()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for booking in bookings:
        writer.writerow(booking_export_row(booking, today))
    # UTF-8 BOM so Excel/Numbers detect Spanish characters correctly.
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
