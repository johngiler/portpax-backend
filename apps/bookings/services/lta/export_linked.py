"""Export bookings linked to a LongTermAgreement (Excel / CSV)."""

from __future__ import annotations

import csv
import re
from io import BytesIO, StringIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.bookings.models import Booking, BookingStatus, LongTermAgreement
from apps.bookings.services.booking_export import STATUS_LABELS_ES, _format_time
from apps.catalogs.utils.position_code import position_short_code

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
    "Tipo de regla",
    "Acuerdo",
]


def _slug_filename(value: str) -> str:
    text = re.sub(r"[^\w\-]+", "-", (value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-").lower()
    return text[:80] or "acuerdo"


def _extra_dates(agreement: LongTermAgreement) -> set[str]:
    out: set[str] = set()
    for item in agreement.date_exceptions or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").lower() != "include":
            continue
        raw = item.get("date")
        if raw:
            out.add(str(raw)[:10])
    return out


def _rule_type(booking: Booking, extras: set[str]) -> str:
    call = booking.call_date.isoformat() if booking.call_date else ""
    return "Extra" if call in extras else "Según acuerdo"


def _position_label(booking: Booking) -> str:
    if not booking.position_id or not booking.position:
        return ""
    port_code = ""
    if booking.port_id and booking.port:
        port_code = booking.port.code or ""
    if port_code:
        return position_short_code(port_code, booking.position.code)
    return booking.position.code


def _row(booking: Booking, agreement: LongTermAgreement, extras: set[str]) -> list:
    return [
        booking.booking_code,
        STATUS_LABELS_ES.get(booking.status, booking.get_status_display()),
        booking.port.name if booking.port_id else "",
        booking.shipping_line.name if booking.shipping_line_id else "",
        booking.vessel.name if booking.vessel_id else "",
        _position_label(booking),
        booking.call_date.isoformat() if booking.call_date else "",
        _format_time(booking.eta),
        _format_time(booking.etd),
        _rule_type(booking, extras),
        agreement.code,
    ]


def linked_bookings_queryset(agreement: LongTermAgreement):
    return (
        Booking.objects.filter(long_term_agreement_id=agreement.pk)
        .exclude(status=BookingStatus.C)
        .select_related("port", "shipping_line", "vessel", "position")
        .order_by("call_date", "id")
    )


def export_linked_filename(agreement: LongTermAgreement, fmt: str) -> str:
    stamp = timezone.localdate().isoformat()
    return f"lta-{_slug_filename(agreement.code)}-reservas-{stamp}.{fmt}"


def build_linked_bookings_xlsx(agreement: LongTermAgreement) -> bytes:
    extras = _extra_dates(agreement)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reservas del acuerdo"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for booking in linked_bookings_queryset(agreement).iterator(chunk_size=200):
        sheet.append(_row(booking, agreement, extras))
    for column_cells in sheet.columns:
        max_len = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        sheet.column_dimensions[column_letter].width = min(max_len + 2, 48)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_linked_bookings_csv(agreement: LongTermAgreement) -> bytes:
    extras = _extra_dates(agreement)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for booking in linked_bookings_queryset(agreement).iterator(chunk_size=200):
        writer.writerow(_row(booking, agreement, extras))
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
