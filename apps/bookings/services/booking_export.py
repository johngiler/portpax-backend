"""Export bookings list to Excel (.xlsx) or CSV."""

from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO

from django.utils import timezone

from apps.bookings.constants import ACTIVE_BOOKING_STATUSES
from apps.bookings.models import Booking, BookingStatus

HEADERS = [
    "Código",
    "Estado",
    "Puerto",
    "Naviera",
    "Barco",
    "Tamaño",
    "Cap. máx.",
    "Eslora (m)",
    "Manga (m)",
    "Calado (m)",
    "GT",
    "Trip. máx.",
    "Posición",
    "Fecha de escala",
    "ETA",
    "ETD",
    "ETA real",
    "ETD real",
    "PAX planificado",
    "PAX real",
    "Tripulación real",
    "Motivo de cancelación",
    "Comentario de cancelación",
    "Notas",
    "Creado",
    "Actualizado",
]

STATUS_LABELS_ES = {
    BookingStatus.NR: "Nueva solicitud",
    BookingStatus.H: "Hold",
    BookingStatus.CO: "Confirmada",
    BookingStatus.CL: "Confirmada LTA",
    BookingStatus.LTA: "LTA",
    BookingStatus.LTD: "Long Term Deployment",
    BookingStatus.R: "Real",
    BookingStatus.C: "Cancelada",
}


def _status_label(booking: Booking, today: date) -> str:
    if booking.status == BookingStatus.C:
        return STATUS_LABELS_ES[BookingStatus.C]
    if booking.status == BookingStatus.R:
        return STATUS_LABELS_ES[BookingStatus.R]
    if booking.call_date < today and booking.status in ACTIVE_BOOKING_STATUSES:
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


def _format_call_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def vessel_size_label(booking: Booking) -> str:
    """Catalog ``Vessel.size_category`` for booking row exports."""
    vessel = booking.vessel
    if vessel is None:
        return ""
    return (vessel.size_category or "").strip()


def booking_export_row(
    booking: Booking,
    today: date | None = None,
    *,
    include_cancellation: bool = False,
) -> list:
    today = today or timezone.localdate()
    vessel = booking.vessel
    row = [
        booking.booking_code,
        _status_label(booking, today),
        booking.port.name,
        booking.shipping_line.name,
        vessel.name if vessel is not None else "",
        vessel_size_label(booking),
        _cell_value(vessel.pax_capacity if vessel is not None else None),
        _cell_value(vessel.loa_m if vessel is not None else None),
        _cell_value(vessel.beam_m if vessel is not None else None),
        _cell_value(vessel.draft_m if vessel is not None else None),
        _cell_value(vessel.gross_tonnage if vessel is not None else None),
        _cell_value(vessel.crew_capacity if vessel is not None else None),
        booking.position.code if booking.position_id else "",
        _format_call_date(booking.call_date),
        _format_time(booking.eta),
        _format_time(booking.etd),
        _format_time(booking.eta_real),
        _format_time(booking.etd_real),
        _cell_value(booking.planned_pax),
        _cell_value(booking.actual_pax),
        _cell_value(booking.actual_crew),
    ]
    if include_cancellation:
        row.extend(
            [
                booking.get_cancellation_reason_display()
                if booking.cancellation_reason
                else "",
                booking.cancellation_notes or "",
            ]
        )
    row.extend(
        [
            booking.notes or "",
            _format_datetime(booking.created_at),
            _format_datetime(booking.updated_at),
        ]
    )
    return row


def _csv_headers(*, include_cancellation: bool) -> list[str]:
    if include_cancellation:
        return list(HEADERS)
    skip = {"Motivo de cancelación", "Comentario de cancelación"}
    return [header for header in HEADERS if header not in skip]


def build_bookings_xlsx(
    bookings,
    overview=None,
    *,
    pax_basis: str = "planned",
    include_cancellation: bool = False,
) -> bytes:
    from apps.bookings.services.arrivals_pdf.list_xlsx import build_arrivals_list_xlsx

    return build_arrivals_list_xlsx(
        bookings,
        overview=overview,
        pax_basis=pax_basis,
        include_cancellation=include_cancellation,
    )


def build_bookings_csv(bookings, *, include_cancellation: bool = False) -> bytes:
    today = timezone.localdate()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_csv_headers(include_cancellation=include_cancellation))
    for booking in bookings:
        writer.writerow(
            booking_export_row(
                booking, today, include_cancellation=include_cancellation
            )
        )
    # UTF-8 BOM so Excel/Numbers detect Spanish characters correctly.
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
