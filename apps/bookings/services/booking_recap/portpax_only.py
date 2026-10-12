"""Bookings in PortPax that fall in the recap window but were not matched."""

from __future__ import annotations

from datetime import date
from typing import Any

from apps.bookings.models import Booking
from apps.bookings.services.booking_export import STATUS_LABELS_ES
from apps.bookings.services.validation.legend_labels import port_legend_label


def _hhmm(value) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


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
) -> list[dict[str, Any]]:
    """
    Elasticity when both Desde and Hasta are set: list PortPax bookings in
    that range that the recap did not pair.

    Always biased to ports seen in the paste. Carrier scope:
    explicit line/group delimiters, else lines resolved from the recap rows.
    Without a usable carrier scope, returns [] (port-only would flood).
    """
    if not date_from or not date_to or date_from > date_to:
        return []
    if not recap_port_ids:
        return []

    port_ids = set(recap_port_ids)
    if allowed_ports is not None:
        port_ids &= set(allowed_ports)
    if not port_ids:
        return []

    line_ids = [int(x) for x in shipping_line_ids if int(x) > 0]
    group_ids = [int(x) for x in shipping_line_group_ids if int(x) > 0]
    inferred_lines = sorted(int(x) for x in recap_line_ids if int(x) > 0)

    qs = Booking.objects.filter(
        port_id__in=port_ids,
        call_date__gte=date_from,
        call_date__lte=date_to,
    ).select_related("vessel", "port", "shipping_line")
    if matched_ids:
        qs = qs.exclude(id__in=matched_ids)
    if line_ids:
        qs = qs.filter(shipping_line_id__in=line_ids)
    elif group_ids:
        qs = qs.filter(shipping_line__group_id__in=group_ids)
    elif inferred_lines:
        qs = qs.filter(shipping_line_id__in=inferred_lines)
    else:
        return []

    rows: list[dict[str, Any]] = []
    for booking in qs.order_by("call_date", "id"):
        port = booking.port
        port_name = (port_legend_label(port) or "").strip() or (
            getattr(port, "name", None) or "Puerto"
        )
        vessel = booking.vessel
        line = booking.shipping_line
        rows.append(
            {
                "booking_id": booking.id,
                "booking_code": booking.booking_code or "",
                "vessel_name": getattr(vessel, "name", None) or "",
                "port_name": port_name,
                "shipping_line_name": getattr(line, "name", None) or "",
                "call_date": booking.call_date.isoformat()
                if booking.call_date
                else None,
                "eta": _hhmm(booking.eta),
                "etd": _hhmm(booking.etd),
                "status": booking.status,
                "status_display": STATUS_LABELS_ES.get(
                    booking.status, booking.get_status_display()
                ),
            }
        )
    return rows
