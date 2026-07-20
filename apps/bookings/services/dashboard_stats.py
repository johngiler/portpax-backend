"""Aggregate operational metrics for the Dashboard."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, QuerySet, Sum

from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.catalogs.models import Port, Position, PositionType

OCCUPANCY_STATUSES = (
    BookingStatus.CO,
    BookingStatus.CL,
    BookingStatus.LTA,
    BookingStatus.LTD,
    BookingStatus.R,
)

CONFIRMED_FORWARD_STATUSES = (
    BookingStatus.CO,
    BookingStatus.CL,
    BookingStatus.LTA,
    BookingStatus.LTD,
)


def _shift_year(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 Feb → 28 Feb on non-leap years
        return d.replace(year=d.year + years, month=2, day=28)


def _delta_pct(current: float | int, prior: float | int) -> float | None:
    if prior == 0:
        return None if current == 0 else 100.0
    return round(((current - prior) / prior) * 100, 1)


def _apply_scope(
    qs: QuerySet,
    *,
    port_id: int | None,
    shipping_line_id: int | None,
    shipping_line_group_id: int | None,
    allowed_ports: list[int] | None,
) -> QuerySet:
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(port_id=port_id)
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    elif shipping_line_group_id:
        qs = qs.filter(shipping_line__group_id=shipping_line_group_id)
    return qs


def _port_display(row: dict) -> str:
    return row.get("port__commercial_name") or row["port__name"]


def build_dashboard_stats(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
    allowed_ports: list[int] | None = None,
    today: date | None = None,
) -> dict:
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    today = today or date.today()
    scope_kwargs = {
        "port_id": port_id,
        "shipping_line_id": shipping_line_id,
        "shipping_line_group_id": shipping_line_group_id,
        "allowed_ports": allowed_ports,
    }

    qs = _apply_scope(
        Booking.objects.filter(call_date__gte=date_from, call_date__lte=date_to),
        **scope_kwargs,
    )

    status_counts = {
        row["status"]: row["c"]
        for row in qs.values("status").annotate(c=Count("id"))
    }
    nr = status_counts.get(BookingStatus.NR, 0)
    hold = status_counts.get(BookingStatus.H, 0)
    confirmed = status_counts.get(BookingStatus.CO, 0)
    confirmed_lta = status_counts.get(BookingStatus.CL, 0)
    lta = status_counts.get(BookingStatus.LTA, 0)
    ltd = status_counts.get(BookingStatus.LTD, 0)
    real = status_counts.get(BookingStatus.R, 0)
    cancelled = status_counts.get(BookingStatus.C, 0)
    total = nr + hold + confirmed + confirmed_lta + lta + ltd + real + cancelled

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
    if allowed_ports is not None:
        positions_qs = positions_qs.filter(port_id__in=allowed_ports)
    if port_id:
        positions_qs = positions_qs.filter(port_id=port_id)
    position_count = positions_qs.count()
    day_count = (date_to - date_from).days + 1
    capacity_slot_days = position_count * day_count
    occupied_slot_days = qs.filter(status__in=OCCUPANCY_STATUSES).count()
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
    if allowed_ports is not None:
        ports_in_scope = ports_in_scope.filter(id__in=allowed_ports)
    if port_id:
        ports_in_scope = ports_in_scope.filter(id=port_id)

    # --- Spec 7.7: action queue (open Hold / NR from today) ---
    forward_base = _apply_scope(Booking.objects.all(), **scope_kwargs)
    holds_open = forward_base.filter(status=BookingStatus.H, call_date__gte=today)
    nr_open = forward_base.filter(status=BookingStatus.NR, call_date__gte=today)
    action_by_port_map: dict[int, dict] = {}
    for row in (
        holds_open.values("port_id", "port__name", "port__code", "port__commercial_name")
        .annotate(holds=Count("id"))
        .order_by("-holds")
    ):
        action_by_port_map[row["port_id"]] = {
            "port_id": row["port_id"],
            "name": _port_display(row),
            "code": row["port__code"],
            "holds": row["holds"],
            "new_requests": 0,
        }
    for row in (
        nr_open.values("port_id", "port__name", "port__code", "port__commercial_name")
        .annotate(new_requests=Count("id"))
        .order_by("-new_requests")
    ):
        entry = action_by_port_map.get(row["port_id"])
        if entry:
            entry["new_requests"] = row["new_requests"]
        else:
            action_by_port_map[row["port_id"]] = {
                "port_id": row["port_id"],
                "name": _port_display(row),
                "code": row["port__code"],
                "holds": 0,
                "new_requests": row["new_requests"],
            }
    action_by_port = sorted(
        action_by_port_map.values(),
        key=lambda r: (r["holds"] + r["new_requests"]),
        reverse=True,
    )

    # --- Spec 7.7: next 30 days confirmed by port ---
    horizon_to = today + timedelta(days=29)
    next_qs = forward_base.filter(
        call_date__gte=today,
        call_date__lte=horizon_to,
        status__in=CONFIRMED_FORWARD_STATUSES,
    )
    next_by_port = [
        {
            "port_id": row["port_id"],
            "name": _port_display(row),
            "code": row["port__code"],
            "calls": row["calls"],
            "planned_pax": row["planned_pax"] or 0,
        }
        for row in (
            next_qs.values("port_id", "port__name", "port__code", "port__commercial_name")
            .annotate(calls=Count("id"), planned_pax=Sum("planned_pax"))
            .order_by("-calls")
        )
    ]
    next_agg = next_qs.aggregate(calls=Count("id"), planned_pax=Sum("planned_pax"))

    # --- Spec 7.7: YoY vs same calendar window prior year ---
    prior_from = _shift_year(date_from, -1)
    prior_to = _shift_year(date_to, -1)
    prior_qs = _apply_scope(
        Booking.objects.filter(call_date__gte=prior_from, call_date__lte=prior_to),
        **scope_kwargs,
    )
    prior_active = prior_qs.exclude(status=BookingStatus.C)
    prior_calls = prior_active.count()
    prior_pax = prior_active.aggregate(planned=Sum("planned_pax"))["planned"] or 0
    current_calls = active_qs.count()

    # --- Occupancy by port (period filter) ---
    pier_by_port = {
        row["port_id"]: row["c"]
        for row in positions_qs.values("port_id").annotate(c=Count("id"))
    }
    occupied_by_port = {
        row["port_id"]: row["c"]
        for row in qs.filter(status__in=OCCUPANCY_STATUSES)
        .values("port_id")
        .annotate(c=Count("id"))
    }
    occupancy_by_port = []
    for port in ports_in_scope.order_by("name"):
        pier_count = pier_by_port.get(port.id, 0)
        capacity = pier_count * day_count
        occupied = occupied_by_port.get(port.id, 0)
        occupancy_by_port.append(
            {
                "port_id": port.id,
                "name": port.commercial_name or port.name,
                "code": port.code,
                "position_count": pier_count,
                "capacity_slot_days": capacity,
                "occupied_slot_days": occupied,
                "occupancy_pct": (
                    round((occupied / capacity) * 100, 1) if capacity > 0 else 0.0
                ),
            }
        )
    occupancy_by_port.sort(key=lambda r: r["occupancy_pct"], reverse=True)

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
        "action_queue": {
            "as_of": today.isoformat(),
            "holds": holds_open.count(),
            "new_requests": nr_open.count(),
            "by_port": action_by_port,
        },
        "next_30_days": {
            "date_from": today.isoformat(),
            "date_to": horizon_to.isoformat(),
            "total_confirmed": next_agg["calls"] or 0,
            "planned_pax": next_agg["planned_pax"] or 0,
            "by_port": next_by_port,
        },
        "yoy": {
            "prior_date_from": prior_from.isoformat(),
            "prior_date_to": prior_to.isoformat(),
            "calls": {
                "current": current_calls,
                "prior": prior_calls,
                "delta_pct": _delta_pct(current_calls, prior_calls),
            },
            "planned_pax": {
                "current": planned_pax,
                "prior": prior_pax,
                "delta_pct": _delta_pct(planned_pax, prior_pax),
            },
        },
        "occupancy_by_port": occupancy_by_port,
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
            {"status": "cl", "label": "Confirmadas LTA", "count": confirmed_lta},
            {"status": "lta", "label": "LTA", "count": lta},
            {"status": "ltd", "label": "Long Term Deployment", "count": ltd},
            {"status": "r", "label": "Real", "count": real},
            {"status": "c", "label": "Canceladas", "count": cancelled},
        ],
    }
