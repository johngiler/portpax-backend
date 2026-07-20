"""Aggregate operational metrics for the Dashboard prototype."""

from __future__ import annotations

from datetime import date

from django.db.models import Count, Sum

from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.catalogs.models import Port, Position, PositionType


def build_dashboard_stats(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
) -> dict:
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    qs = Booking.objects.filter(call_date__gte=date_from, call_date__lte=date_to)

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
    nr = status_counts.get(BookingStatus.NR, 0)
    hold = status_counts.get(BookingStatus.H, 0)
    confirmed = status_counts.get(BookingStatus.CO, 0)
    real = status_counts.get(BookingStatus.R, 0)
    cancelled = status_counts.get(BookingStatus.C, 0)
    total = nr + hold + confirmed + real + cancelled

    active_qs = qs.exclude(status=BookingStatus.C)
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
    day_count = (date_to - date_from).days + 1
    capacity_slot_days = position_count * day_count
    occupied_slot_days = qs.filter(
        status__in=[BookingStatus.CO, BookingStatus.R],
    ).count()
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
        m: {"nr": 0, "h": 0, "co": 0, "r": 0, "c": 0, "total": 0}
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
        qs.filter(status=BookingStatus.C)
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

    years = sorted({date_from.year, date_to.year})

    return {
        "years": years,
        "year": years[0] if len(years) == 1 else None,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "day_count": day_count,
        "kpis": {
            "occupancy_pct": occupancy_pct,
            "capacity_slot_days": capacity_slot_days,
            "occupied_slot_days": occupied_slot_days,
            "position_count": position_count,
            "total_bookings": total,
            "nr": nr,
            "h": hold,
            "co": confirmed,
            "r": real,
            "c": cancelled,
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
            {"status": "nr", "label": "Nuevas solicitudes", "count": nr},
            {"status": "h", "label": "Hold", "count": hold},
            {"status": "co", "label": "Confirmadas", "count": confirmed},
            {"status": "r", "label": "Real", "count": real},
            {"status": "c", "label": "Canceladas", "count": cancelled},
        ],
    }
