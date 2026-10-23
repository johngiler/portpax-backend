"""Bookings in PortPax that fall in the recap window but were not matched."""

from __future__ import annotations

from datetime import date
from typing import Any

from apps.bookings.constants import ACTIVE_BOOKING_STATUSES
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking_export import STATUS_LABELS_ES
from apps.bookings.services.validation.legend_labels import port_legend_label

DEFAULT_PORTPAX_ONLY_PAGE_SIZE = 10

# Commercial recap: ghost LTA slots are not confirmed yet (Beto).
RECAP_PORTPAX_ONLY_STATUSES = tuple(
    status
    for status in ACTIVE_BOOKING_STATUSES
    if status != BookingStatus.LTA
)


def _hhmm(value) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _serialize_portpax_only_row(booking: Booking) -> dict[str, Any]:
    port = booking.port
    port_name = (port_legend_label(port) or "").strip() or (
        getattr(port, "name", None) or "Puerto"
    )
    vessel = booking.vessel
    line = booking.shipping_line
    return {
        "booking_id": booking.id,
        "booking_code": booking.booking_code or "",
        "vessel_name": getattr(vessel, "name", None) or "",
        "port_id": port.id if port else None,
        "port_name": port_name,
        "shipping_line_name": getattr(line, "name", None) or "",
        "call_date": booking.call_date.isoformat() if booking.call_date else None,
        "eta": _hhmm(booking.eta),
        "etd": _hhmm(booking.etd),
        "status": booking.status,
        "status_display": STATUS_LABELS_ES.get(
            booking.status, booking.get_status_display()
        ),
    }


def find_portpax_only_bookings(
    *,
    date_from: date | None,
    date_to: date | None,
    recap_port_ids: set[int],
    recap_line_ids: set[int],
    matched_ids: set[int],
    shipping_line_ids: list[int],
    shipping_line_group_ids: list[int],
    allowed_ports: set[int] | None,
    page: int = 1,
    page_size: int = DEFAULT_PORTPAX_ONLY_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], int]:
    """
    Elasticity when both Desde and Hasta are set: list PortPax bookings in
    that range that the recap did not pair.

    Always biased to ports seen in the paste (port column). Carrier scope:
    - explicit line/group delimiters in the modal → those only;
    - otherwise → all lines at those ports in the date window (so a missing
      carrier that never appeared in the paste, e.g. Costa, still surfaces).

    ``recap_line_ids`` is kept for call-site compatibility; it no longer
    narrows the query when no explicit carrier filter is set.

    Paginated (``page`` / ``page_size``). Returns ``(page_rows, total_count)``.

    Excludes Cancelada and Real — only active/planned statuses (ops still
    expect them on a commercial recap).

    Ghost LTA slots (status LTA) are not confirmed yet — omit them (Beto).
    Confirmada LTA (CL) stays.
    """
    if not date_from or not date_to or date_from > date_to:
        return [], 0
    if not recap_port_ids:
        return [], 0

    port_ids = set(recap_port_ids)
    if allowed_ports is not None:
        port_ids &= set(allowed_ports)
    if not port_ids:
        return [], 0

    line_ids = [int(x) for x in shipping_line_ids if int(x) > 0]
    group_ids = [int(x) for x in shipping_line_group_ids if int(x) > 0]
    # recap_line_ids: kept for call-site compat; not used when no explicit filter.

    qs = Booking.objects.filter(
        port_id__in=port_ids,
        call_date__gte=date_from,
        call_date__lte=date_to,
        status__in=RECAP_PORTPAX_ONLY_STATUSES,
    ).select_related("vessel", "port", "shipping_line")
    if matched_ids:
        qs = qs.exclude(id__in=matched_ids)
    if line_ids:
        qs = qs.filter(shipping_line_id__in=line_ids)
    elif group_ids:
        qs = qs.filter(shipping_line__group_id__in=group_ids)

    qs = qs.order_by("call_date", "id")
    total = qs.count()
    if total <= 0:
        return [], 0

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or DEFAULT_PORTPAX_ONLY_PAGE_SIZE), 100))
    offset = (page - 1) * page_size
    page_rows = [
        _serialize_portpax_only_row(booking)
        for booking in qs[offset : offset + page_size]
    ]
    return page_rows, total
