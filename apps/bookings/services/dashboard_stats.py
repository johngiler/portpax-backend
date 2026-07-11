"""Aggregate operational metrics for the Dashboard prototype."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from django.db.models import Count, Q, Sum

from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.catalogs.models import Port, Position, PositionType


def _year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def _days_in_year(year: int) -> int:
    return 366 if monthrange(year, 2)[1] == 29 else 365


def build_dashboard_stats(
    *,
    years: list[int],
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
) -> dict:
    years = sorted({int(y) for y in years})
    if not years:
        years = [date.today().year]

    year_q = Q()
    for year in years:
        date_from, date_to = _year_bounds(year)
        year_q |= Q(call_date__gte=date_from, call_date__lte=date_to)

    qs = Booking.objects.filter(year_q)
    range_from = _year_bounds(years[0])[0]
    range_to = _year_bounds(years[-1])[1]

    if port_id:
        qs = qs.filter(port_id=port_id)
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    elif shipping_line_group_id:
        qs = qs.filter(shipping_line__group_id=shipping_line_group_id)

    status_counts = {
        row["status"]: row["c"]
        for row in qs.values("status").annotate(c=Count("id"))
    }
    requested = status_counts.get(BookingStatus.REQUESTED, 0)
    confirmed = status_counts.get(BookingStatus.CONFIRMED, 0)
    cancelled = status_counts.get(BookingStatus.CANCELLED, 0)
    total = requested + confirmed + cancelled

    active_qs = qs.exclude(status=BookingStatus.CANCELLED)
    pax_agg = active_qs.aggregate(
        planned=Sum("planned_pax"),
        actual=Sum("actual_pax"),
    )
    planned_pax = pax_agg["planned"] or 0
    actual_pax = pax_agg["actual"] or 0

    positions_qs = Position.objects.filter(
        is_active=True,
        position_type=PositionType.PIER,
        port__is_active=True,
    )
    if port_id:
        positions_qs = positions_qs.filter(port_id=port_id)
    position_count = positions_qs.count()
    capacity_slot_days = position_count * sum(_days_in_year(y) for y in years)
    occupied_slot_days = qs.filter(status=BookingStatus.CONFIRMED).count()
    occupancy_pct = (
        round((occupied_slot_days / capacity_slot_days) * 100, 1)
        if capacity_slot_days > 0
        else 0.0
    )

    by_line = list(
        active_qs.values(
            "shipping_line_id",
            "shipping_line__name",
            "shipping_line__code",
        )
        .annotate(
            bookings=Count("id"),
            planned_pax=Sum("planned_pax"),
        )
        .order_by("-bookings")[:12]
    )

    by_month_raw = (
        qs.values("call_date__month", "status")
        .annotate(c=Count("id"))
        .order_by("call_date__month")
    )
    month_map: dict[int, dict[str, int]] = {
        m: {"requested": 0, "confirmed": 0, "cancelled": 0, "total": 0}
        for m in range(1, 13)
    }
    for row in by_month_raw:
        month = row["call_date__month"]
        status = row["status"]
        count = row["c"]
        if status in month_map[month]:
            month_map[month][status] = count
        month_map[month]["total"] += count
    by_month = [{"month": m, **month_map[m]} for m in range(1, 13)]

    top_vessels = list(
        active_qs.values(
            "vessel_id",
            "vessel__name",
            "shipping_line__name",
        )
        .annotate(
            bookings=Count("id"),
            planned_pax=Sum("planned_pax"),
        )
        .order_by("-bookings")[:8]
    )

    by_port = list(
        active_qs.values("port_id", "port__name", "port__code", "port__commercial_name")
        .annotate(bookings=Count("id"))
        .order_by("-bookings")[:10]
    )

    cancel_reasons = list(
        qs.filter(status=BookingStatus.CANCELLED)
        .exclude(cancellation_reason="")
        .values("cancellation_reason")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    reason_labels = dict(CancellationReason.choices)
    by_cancellation_reason = [
        {
            "reason": row["cancellation_reason"],
            "label": reason_labels.get(row["cancellation_reason"], row["cancellation_reason"]),
            "count": row["c"],
        }
        for row in cancel_reasons
    ]

    weekday_counts = [0] * 7
    for call_date in active_qs.values_list("call_date", flat=True):
        weekday_counts[call_date.weekday()] += 1
    by_weekday = [
        {"weekday": i, "label": label, "count": weekday_counts[i]}
        for i, label in enumerate(
            ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        )
    ]

    ports_in_scope = Port.objects.filter(is_active=True)
    if port_id:
        ports_in_scope = ports_in_scope.filter(id=port_id)

    return {
        "years": years,
        "year": years[0] if len(years) == 1 else None,
        "date_from": range_from.isoformat(),
        "date_to": range_to.isoformat(),
        "kpis": {
            "occupancy_pct": occupancy_pct,
            "capacity_slot_days": capacity_slot_days,
            "occupied_slot_days": occupied_slot_days,
            "position_count": position_count,
            "total_bookings": total,
            "requested": requested,
            "confirmed": confirmed,
            "cancelled": cancelled,
            "planned_pax": planned_pax,
            "actual_pax": actual_pax,
            "ports_count": ports_in_scope.count(),
        },
        "by_shipping_line": [
            {
                "id": row["shipping_line_id"],
                "name": row["shipping_line__name"],
                "code": row["shipping_line__code"],
                "bookings": row["bookings"],
                "planned_pax": row["planned_pax"] or 0,
            }
            for row in by_line
        ],
        "by_month": by_month,
        "top_vessels": [
            {
                "id": row["vessel_id"],
                "name": row["vessel__name"],
                "shipping_line_name": row["shipping_line__name"],
                "bookings": row["bookings"],
                "planned_pax": row["planned_pax"] or 0,
            }
            for row in top_vessels
        ],
        "by_port": [
            {
                "id": row["port_id"],
                "name": row["port__commercial_name"] or row["port__name"],
                "code": row["port__code"],
                "bookings": row["bookings"],
            }
            for row in by_port
        ],
        "by_cancellation_reason": by_cancellation_reason,
        "by_weekday": by_weekday,
        "status_breakdown": [
            {"status": "requested", "label": "Solicitadas", "count": requested},
            {"status": "confirmed", "label": "Confirmadas", "count": confirmed},
            {"status": "cancelled", "label": "Canceladas", "count": cancelled},
        ],
    }
