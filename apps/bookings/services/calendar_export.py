"""Export operational calendar rows (port + date range) to xlsx/csv."""

from __future__ import annotations

import csv
from datetime import date
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Font

from apps.bookings.models import Booking
from apps.bookings.services.booking_export import STATUS_LABELS_ES, _format_time

HEADERS = [
    "Fecha",
    "Puerto",
    "Muelle",
    "Naviera",
    "Barco",
    "Eslora (m)",
    "Estado",
    "ETA",
    "ETD",
    "PAX planificado",
    "PAX real",
    "Código",
]


def _loa(booking: Booking) -> str:
    loa = booking.vessel.loa_m
    if loa is None:
        return ""
    return str(loa)


def _row(booking: Booking) -> list:
    return [
        booking.call_date.isoformat(),
        booking.port.name,
        booking.position.code if booking.position_id else "Sin asignar",
        booking.shipping_line.name,
        booking.vessel.name,
        _loa(booking),
        STATUS_LABELS_ES.get(booking.status, booking.get_status_display()),
        _format_time(booking.eta),
        _format_time(booking.etd),
        booking.planned_pax if booking.planned_pax is not None else "",
        booking.actual_pax if booking.actual_pax is not None else "",
        booking.booking_code,
    ]


def build_calendar_csv(bookings: list[Booking]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for booking in bookings:
        writer.writerow(_row(booking))
    return buffer.getvalue()


def build_calendar_xlsx(bookings: list[Booking]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Calendario"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for booking in bookings:
        ws.append(_row(booking))
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def calendar_export_filename(
    port_codes: list[str],
    date_from: date,
    date_to: date,
    ext: str,
) -> str:
    if len(port_codes) == 1:
        label = port_codes[0]
    elif 1 < len(port_codes) <= 3:
        label = "_".join(port_codes)
    else:
        label = "multipuerto"
    return f"calendario_{label}_{date_from.isoformat()}_{date_to.isoformat()}.{ext}"
