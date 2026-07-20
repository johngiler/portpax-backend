"""Operational reports: booking totals and weekly status movements."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.db.models import Count, Sum

from apps.audit.models import BookingAuditEntry
from apps.bookings.models import Booking, BookingStatus


def build_booking_totals(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    without_lta: bool = False,
    allowed_ports: set[int] | None = None,
) -> dict:
    qs = Booking.objects.filter(call_date__gte=date_from, call_date__lte=date_to)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(port_id=port_id)
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    if without_lta:
        qs = qs.exclude(
            status__in=[BookingStatus.LTA, BookingStatus.CL, BookingStatus.LTD],
        )

    by_month = (
        qs.values("call_date__year", "call_date__month")
        .annotate(
            calls=Count("id"),
            planned_pax=Sum("planned_pax"),
            actual_pax=Sum("actual_pax"),
        )
        .order_by("call_date__year", "call_date__month")
    )
    by_port = (
        qs.values("port_id", "port__code", "port__name")
        .annotate(calls=Count("id"), planned_pax=Sum("planned_pax"))
        .order_by("-calls")
    )
    by_line = (
        qs.values("shipping_line_id", "shipping_line__code", "shipping_line__name")
        .annotate(calls=Count("id"), planned_pax=Sum("planned_pax"))
        .order_by("-calls")
    )
    by_status = {
        row["status"]: row["c"]
        for row in qs.values("status").annotate(c=Count("id"))
    }

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "total_calls": qs.count(),
        "planned_pax": qs.aggregate(s=Sum("planned_pax"))["s"] or 0,
        "actual_pax": qs.aggregate(s=Sum("actual_pax"))["s"] or 0,
        "by_status": by_status,
        "by_month": [
            {
                "year": row["call_date__year"],
                "month": row["call_date__month"],
                "calls": row["calls"],
                "planned_pax": row["planned_pax"] or 0,
                "actual_pax": row["actual_pax"] or 0,
            }
            for row in by_month
        ],
        "by_port": [
            {
                "port_id": row["port_id"],
                "code": row["port__code"],
                "name": row["port__name"],
                "calls": row["calls"],
                "planned_pax": row["planned_pax"] or 0,
            }
            for row in by_port
        ],
        "by_shipping_line": [
            {
                "shipping_line_id": row["shipping_line_id"],
                "code": row["shipping_line__code"],
                "name": row["shipping_line__name"],
                "calls": row["calls"],
                "planned_pax": row["planned_pax"] or 0,
            }
            for row in by_line
        ],
    }


def build_weekly_movements(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    allowed_ports: set[int] | None = None,
) -> dict:
    qs = BookingAuditEntry.objects.filter(
        action="status_change",
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).select_related(
        "booking",
        "booking__port",
        "booking__shipping_line",
        "booking__vessel",
        "user",
    )
    if allowed_ports is not None:
        qs = qs.filter(booking__port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(booking__port_id=port_id)

    confirmations: list[dict] = []
    cancellations: list[dict] = []
    confirmed_targets = {
        BookingStatus.CO,
        BookingStatus.CL,
        BookingStatus.LTA,
        BookingStatus.LTD,
        BookingStatus.R,
    }

    for entry in qs:
        changes = entry.changes or {}
        status_change = changes.get("status") or {}
        to_status = status_change.get("to")
        if not to_status:
            continue
        booking = entry.booking
        item = {
            "id": entry.id,
            "at": entry.created_at.isoformat(),
            "from_status": status_change.get("from"),
            "to_status": to_status,
            "booking_code": booking.booking_code,
            "call_date": booking.call_date.isoformat(),
            "port_code": booking.port.code,
            "shipping_line_name": booking.shipping_line.name,
            "vessel_name": booking.vessel.name,
            "user": entry.user.get_username() if entry.user_id else None,
        }
        if to_status == BookingStatus.C:
            cancellations.append(item)
        elif to_status in confirmed_targets:
            confirmations.append(item)

    by_line: dict[str, dict] = defaultdict(
        lambda: {"confirmations": 0, "cancellations": 0},
    )
    for row in confirmations:
        by_line[row["shipping_line_name"]]["confirmations"] += 1
    for row in cancellations:
        by_line[row["shipping_line_name"]]["cancellations"] += 1

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "confirmations_count": len(confirmations),
        "cancellations_count": len(cancellations),
        "confirmations": confirmations[:500],
        "cancellations": cancellations[:500],
        "by_shipping_line": [
            {"name": name, **counts} for name, counts in sorted(by_line.items())
        ],
    }
