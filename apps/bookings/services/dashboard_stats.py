"""Aggregate operational metrics for the Dashboard."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, F, IntegerField, QuerySet, Sum
from django.db.models.functions import Coalesce, ExtractYear

from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.bookings.services.dashboard_occupancy import (
    atomic_pier_positions_qs,
    iter_occupancy_booking_rows,
    occupied_physical_slot_days,
)
from apps.bookings.services.dashboard_series import (
    build_by_port_month,
    build_occupancy_trends,
)
from apps.bookings.services.report_exports.common import (
    PAX_BASIS_CAPACITY,
    normalize_pax_basis,
)
from apps.bookings.services.validation.conflict_type_filters import (
    CONFLICT_TYPE_CODES,
)
from apps.catalogs.models import Port

CONFLICT_TYPE_LABELS_ES = {
    "proximity": "Proximidad",
    "loa": "Eslora",
    "schedule": "Horario",
    "position": "Posición",
    "lta": "LTA",
    "physical": "Físico",
}

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


def _merge_ids(
    single: int | None,
    many: list[int] | None,
) -> list[int]:
    ids: list[int] = []
    if many:
        ids.extend(int(value) for value in many if value)
    if single:
        ids.append(int(single))
    # Preserve order, drop duplicates.
    seen: set[int] = set()
    out: list[int] = []
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _avg_pax_per_call(calls: int, pax: int) -> float:
    if calls <= 0:
        return 0.0
    return round(pax / calls, 1)


def _days_in_year_window(year: int, date_from: date, date_to: date) -> int:
    start = max(date_from, date(year, 1, 1))
    end = min(date_to, date(year, 12, 31))
    if end < start:
        return 0
    return (end - start).days + 1


def _apply_scope(
    qs: QuerySet,
    *,
    port_ids: list[int] | None,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    allowed_ports: list[int] | None,
    without_lta: bool = False,
) -> QuerySet:
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_ids:
        qs = qs.filter(port_id__in=port_ids)
    line_ids = _merge_ids(shipping_line_id, shipping_line_ids)
    group_ids = _merge_ids(shipping_line_group_id, shipping_line_group_ids)
    # Lines win over groups (same rule as list / reports).
    if line_ids:
        qs = qs.filter(shipping_line_id__in=line_ids)
    elif group_ids:
        qs = qs.filter(shipping_line__group_id__in=group_ids)
    if without_lta:
        # Ghost LTA slots only; CL (confirmed) stays in the totals.
        qs = qs.exclude(status=BookingStatus.LTA)
    return qs


def _projected_pax_expr(pax_basis: str):
    """Projected PAX for dashboard aggregates (not manifested actual)."""
    if normalize_pax_basis(pax_basis) == PAX_BASIS_CAPACITY:
        return Coalesce(F("vessel__pax_capacity"), 0, output_field=IntegerField())
    return Coalesce(F("planned_pax"), 0, output_field=IntegerField())


def _sum_projected_pax(qs: QuerySet, pax_basis: str) -> int:
    total = qs.aggregate(total=Sum(_projected_pax_expr(pax_basis)))["total"]
    return int(total or 0)


def _port_display(row: dict) -> str:
    return row.get("port__commercial_name") or row["port__name"]


def _media_url(request, field) -> str | None:
    if not field:
        return None
    try:
        url = field.url
    except ValueError:
        return None
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _port_logo_map(port_ids: list[int], request=None) -> dict[int, str | None]:
    if not port_ids:
        return {}
    return {
        port.id: _media_url(request, port.logo)
        for port in Port.objects.filter(id__in=port_ids).only("id", "logo")
    }


def _attach_port_logos(
    rows: list[dict],
    *,
    request=None,
) -> list[dict]:
    logos = _port_logo_map([row["port_id"] for row in rows], request)
    for row in rows:
        row["logo"] = logos.get(row["port_id"])
    return rows


def _peak_pax_by_port(
    active_qs: QuerySet,
    *,
    today: date,
    pax_basis: str = "planned",
) -> list[dict]:
    """
    Per port: day with the most passengers inside the already-scoped queryset.

    Past call_date → prefer sum(actual_pax); if none manifested, fall back to
    projected PAX (planned or vessel capacity per pax_basis).
    Today / future → sum(projected PAX).
    """
    projected_label = (
        "cap. máx."
        if normalize_pax_basis(pax_basis) == PAX_BASIS_CAPACITY
        else "planificado"
    )
    day_rows = (
        active_qs.values(
            "port_id",
            "call_date",
            "port__name",
            "port__code",
            "port__commercial_name",
        )
        .annotate(
            calls=Count("id"),
            planned=Coalesce(Sum(_projected_pax_expr(pax_basis)), 0),
            actual=Coalesce(Sum("actual_pax"), 0),
        )
        .order_by("port_id", "call_date")
    )

    best_by_port: dict[int, dict] = {}
    for row in day_rows:
        call_date = row["call_date"]
        planned = int(row["planned"] or 0)
        actual = int(row["actual"] or 0)
        if call_date < today:
            if actual > 0:
                passengers = actual
                base = "real"
            else:
                passengers = planned
                base = projected_label
        else:
            passengers = planned
            base = projected_label

        if passengers <= 0:
            continue

        prev = best_by_port.get(row["port_id"])
        if prev is None or passengers > prev["passengers"]:
            best_by_port[row["port_id"]] = {
                "port_id": row["port_id"],
                "name": _port_display(row),
                "code": row["port__code"],
                "call_date": call_date.isoformat(),
                "calls": row["calls"],
                "passengers": passengers,
                "base_pax": base,
            }

    return sorted(
        best_by_port.values(),
        key=lambda r: r["passengers"],
        reverse=True,
    )


def _conflict_summary(qs: QuerySet) -> dict:
    """Bookings with has_conflict in scope: total + counts per filter type."""
    code_to_types: dict[str, list[str]] = {}
    for type_key, codes in CONFLICT_TYPE_CODES.items():
        for code in codes:
            code_to_types.setdefault(code, []).append(type_key)

    type_counts = {key: 0 for key in CONFLICT_TYPE_CODES}
    total = 0
    for snapshot in (
        qs.filter(has_conflict=True)
        .exclude(status=BookingStatus.C)
        .values_list("conflict_snapshot", flat=True)
        .iterator(chunk_size=500)
    ):
        total += 1
        found: set[str] = set()
        for item in snapshot or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            for type_key in code_to_types.get(code, ()):
                found.add(type_key)
        for type_key in found:
            type_counts[type_key] += 1

    by_type = [
        {
            "type": type_key,
            "label": CONFLICT_TYPE_LABELS_ES.get(type_key, type_key),
            "count": type_counts[type_key],
        }
        for type_key in CONFLICT_TYPE_CODES
        if type_counts[type_key] > 0
    ]
    by_type.sort(key=lambda row: row["count"], reverse=True)
    return {"total": total, "by_type": by_type}


def build_dashboard_stats(
    *,
    date_from: date,
    date_to: date,
    port_ids: list[int] | None = None,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    allowed_ports: list[int] | None = None,
    without_lta: bool = False,
    pax_basis: str = "planned",
    today: date | None = None,
    request=None,
) -> dict:
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    today = today or date.today()
    from apps.bookings.services.booking.viewer_scope import (
        apply_viewer_open_market_filter,
        clamp_viewer_open_market_range,
    )

    actor = getattr(request, "user", None)
    date_from, date_to = clamp_viewer_open_market_range(
        actor, date_from, date_to, today=today
    )
    basis = normalize_pax_basis(pax_basis)
    scoped_ports = [int(p) for p in (port_ids or []) if p]
    line_ids = _merge_ids(shipping_line_id, shipping_line_ids)
    group_ids = _merge_ids(shipping_line_group_id, shipping_line_group_ids)
    scope_kwargs = {
        "port_ids": scoped_ports or None,
        "shipping_line_ids": line_ids or None,
        "shipping_line_group_ids": group_ids or None,
        "allowed_ports": allowed_ports,
        "without_lta": without_lta,
    }
    projected_pax = _projected_pax_expr(basis)

    qs = apply_viewer_open_market_filter(
        _apply_scope(
            Booking.objects.filter(call_date__gte=date_from, call_date__lte=date_to),
            **scope_kwargs,
        ),
        actor,
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
    planned_pax = _sum_projected_pax(active_qs, basis)
    actual_pax = active_qs.aggregate(actual=Sum("actual_pax"))["actual"] or 0

    positions_qs = atomic_pier_positions_qs(
        port_ids=scoped_ports or None,
        allowed_ports=allowed_ports,
    )
    position_count = positions_qs.count()
    day_count = max(0, (date_to - date_from).days + 1)
    capacity_slot_days = position_count * day_count
    occupancy_rows = iter_occupancy_booking_rows(
        qs.filter(status__in=OCCUPANCY_STATUSES)
    )
    occupied_slot_days, occupied_by_port_map = occupied_physical_slot_days(
        occupancy_rows
    )
    occupancy_pct = (
        round((occupied_slot_days / capacity_slot_days) * 100, 1)
        if capacity_slot_days > 0
        else 0.0
    )

    by_line_raw = list(
        active_qs.values(
            "shipping_line_id",
            "shipping_line__name",
            "shipping_line__code",
        )
        .annotate(
            bookings=Count("id"),
            planned_pax=Sum(projected_pax),
        )
        .order_by("-planned_pax", "-bookings")[:12]
    )
    by_line = []
    for row in by_line_raw:
        bookings = int(row["bookings"] or 0)
        planned = int(row["planned_pax"] or 0)
        by_line.append(
            {
                **row,
                "avg_planned_pax": round(planned / bookings) if bookings else 0,
            }
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
            planned_pax=Sum(projected_pax),
        )
        .order_by("-planned_pax", "-bookings")[:8]
    )

    by_port = list(
        active_qs.values("port_id", "port__name", "port__code", "port__commercial_name")
        .annotate(bookings=Count("id"))
        .order_by("-bookings")[:10]
    )

    first_arrival_qs = qs.filter(first_arrival=True)
    first_arrivals_count = first_arrival_qs.count()
    first_arrivals_by_port_raw = list(
        first_arrival_qs.values(
            "port_id", "port__name", "port__code", "port__commercial_name"
        )
        .annotate(bookings=Count("id"))
        .order_by("-bookings")[:10]
    )

    cancel_base = qs.filter(status=BookingStatus.C).exclude(cancellation_reason="")
    cancel_reasons = list(
        cancel_base.values("cancellation_reason")
        .annotate(
            c=Count("id"),
            planned_pax=Sum(projected_pax),
        )
        .order_by("-c")
    )
    reason_labels = dict(CancellationReason.choices)
    by_cancellation_reason = []
    for row in cancel_reasons:
        reason = row["cancellation_reason"]
        subset = cancel_base.filter(cancellation_reason=reason)
        top_port = (
            subset.values("port__name", "port__commercial_name")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        top_line = (
            subset.values("shipping_line__name")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        by_cancellation_reason.append(
            {
                "reason": reason,
                "label": reason_labels.get(reason, reason),
                "count": row["c"],
                "planned_pax": int(row["planned_pax"] or 0),
                "port_name": (
                    (top_port.get("port__commercial_name") or top_port.get("port__name"))
                    if top_port
                    else None
                ),
                "shipping_line_name": (
                    top_line.get("shipping_line__name") if top_line else None
                ),
            }
        )

    weekday_in_period = [0] * 7
    cursor = date_from
    while cursor <= date_to:
        weekday_in_period[cursor.weekday()] += 1
        cursor += timedelta(days=1)

    weekday_used = [0] * 7
    for call_date in (
        active_qs.values_list("call_date", flat=True).distinct()
    ):
        weekday_used[call_date.weekday()] += 1

    weekday_counts = [0] * 7
    for call_date in active_qs.values_list("call_date", flat=True):
        weekday_counts[call_date.weekday()] += 1
    by_weekday = [
        {
            "weekday": i,
            "label": label,
            "count": weekday_counts[i],
            "days_in_period": weekday_in_period[i],
            "days_used": weekday_used[i],
        }
        for i, label in enumerate(
            ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        )
    ]

    ports_in_scope = Port.objects.filter(is_active=True)
    if allowed_ports is not None:
        ports_in_scope = ports_in_scope.filter(id__in=allowed_ports)
    if scoped_ports:
        ports_in_scope = ports_in_scope.filter(id__in=scoped_ports)

    # --- Pendientes de confirmar: Hold + LTA in dashboard date range ---
    pending_base = apply_viewer_open_market_filter(
        _apply_scope(
            Booking.objects.filter(call_date__gte=date_from, call_date__lte=date_to),
            **scope_kwargs,
        ),
        actor,
    )
    holds_pending = pending_base.filter(status=BookingStatus.H)
    lta_pending = pending_base.filter(status=BookingStatus.LTA)
    pending_by_port_map: dict[int, dict] = {}
    for row in (
        holds_pending.values(
            "port_id", "port__name", "port__code", "port__commercial_name"
        )
        .annotate(holds=Count("id"))
        .order_by("-holds")
    ):
        pending_by_port_map[row["port_id"]] = {
            "port_id": row["port_id"],
            "name": _port_display(row),
            "code": row["port__code"],
            "holds": row["holds"],
            "lta": 0,
        }
    for row in (
        lta_pending.values(
            "port_id", "port__name", "port__code", "port__commercial_name"
        )
        .annotate(lta=Count("id"))
        .order_by("-lta")
    ):
        entry = pending_by_port_map.get(row["port_id"])
        if entry:
            entry["lta"] = row["lta"]
        else:
            pending_by_port_map[row["port_id"]] = {
                "port_id": row["port_id"],
                "name": _port_display(row),
                "code": row["port__code"],
                "holds": 0,
                "lta": row["lta"],
            }
    for entry in pending_by_port_map.values():
        entry["total"] = entry["holds"] + entry["lta"]
    pending_by_port = _attach_port_logos(
        sorted(
            pending_by_port_map.values(),
            key=lambda r: r["total"],
            reverse=True,
        ),
        request=request,
    )
    hold_since = holds_pending.order_by("call_date").values_list(
        "call_date", flat=True
    ).first()
    lta_since = lta_pending.order_by("call_date").values_list(
        "call_date", flat=True
    ).first()
    holds_total = holds_pending.count()
    lta_total = lta_pending.count()

    # Legacy action_queue shape (Hold + NR from today) — kept for older clients.
    forward_base = apply_viewer_open_market_filter(
        _apply_scope(Booking.objects.all(), **scope_kwargs),
        actor,
    )
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

    # --- Spec 7.7: next 30 days removed from dashboard UI (kept out of payload) ---

    # --- Current calendar week (Mon–Sun): ops snap, ignore dashboard filters ---
    week_from = today - timedelta(days=today.weekday())
    week_to = week_from + timedelta(days=6)
    week_qs = apply_viewer_open_market_filter(
        _apply_scope(
            Booking.objects.all(),
            port_ids=None,
            shipping_line_id=None,
            shipping_line_group_id=None,
            allowed_ports=allowed_ports,
        ),
        actor,
    ).filter(
        call_date__gte=week_from,
        call_date__lte=week_to,
        status__in=CONFIRMED_FORWARD_STATUSES,
    )
    week_by_port = [
        {
            "port_id": row["port_id"],
            "name": _port_display(row),
            "code": row["port__code"],
            "calls": row["calls"],
            "planned_pax": row["planned_pax"] or 0,
        }
        for row in (
            week_qs.values("port_id", "port__name", "port__code", "port__commercial_name")
            .annotate(calls=Count("id"), planned_pax=Sum("planned_pax"))
            .order_by("-calls")
        )
    ]
    week_agg = week_qs.aggregate(calls=Count("id"), planned_pax=Sum("planned_pax"))
    iso_week = week_from.isocalendar()[1]

    # --- Peak passengers day per port within dashboard date range ---
    peak_pax_by_port = _attach_port_logos(
        _peak_pax_by_port(active_qs, today=today, pax_basis=basis),
        request=request,
    )

    # --- Spec 7.7: YoY vs same calendar window prior year ---
    prior_from = _shift_year(date_from, -1)
    prior_to = _shift_year(date_to, -1)
    prior_qs = apply_viewer_open_market_filter(
        _apply_scope(
            Booking.objects.filter(call_date__gte=prior_from, call_date__lte=prior_to),
            **scope_kwargs,
        ),
        actor,
    )
    prior_active = prior_qs.exclude(status=BookingStatus.C)
    prior_calls = prior_active.count()
    prior_pax = _sum_projected_pax(prior_active, basis)
    current_calls = active_qs.count()
    avg_pax_per_call = _avg_pax_per_call(current_calls, planned_pax)
    prior_avg_pax_per_call = _avg_pax_per_call(prior_calls, prior_pax)

    calendar_years = list(range(date_from.year, date_to.year + 1))
    by_year_kpis: list[dict] = []
    if len(calendar_years) > 1:
        bookings_by_year = {
            int(row["y"]): int(row["c"] or 0)
            for row in qs.annotate(y=ExtractYear("call_date"))
            .values("y")
            .annotate(c=Count("id"))
        }
        active_by_year = {
            int(row["y"]): {
                "calls": int(row["calls"] or 0),
                "pax": int(row["pax"] or 0),
            }
            for row in active_qs.annotate(y=ExtractYear("call_date"))
            .values("y")
            .annotate(
                calls=Count("id"),
                pax=Sum(projected_pax),
            )
        }
        occupancy_rows_by_year: dict[int, list] = defaultdict(list)
        for row in occupancy_rows:
            occupancy_rows_by_year[row[1].year].append(row)
        occupancy_by_year: dict[int, dict[str, float | int]] = {}
        for year in calendar_years:
            year_days = _days_in_year_window(year, date_from, date_to)
            year_capacity = position_count * year_days
            year_occupied, _ = occupied_physical_slot_days(
                occupancy_rows_by_year.get(year, [])
            )
            occupancy_by_year[year] = {
                "occupied_slot_days": year_occupied,
                "capacity_slot_days": year_capacity,
                "occupancy_pct": (
                    round((year_occupied / year_capacity) * 100, 1)
                    if year_capacity > 0
                    else 0.0
                ),
            }
        first_arrivals_by_year = {
            int(row["y"]): int(row["c"] or 0)
            for row in qs.filter(first_arrival=True)
            .annotate(y=ExtractYear("call_date"))
            .values("y")
            .annotate(c=Count("id"))
        }
        conflicts_by_year = {
            int(row["y"]): int(row["c"] or 0)
            for row in qs.filter(has_conflict=True)
            .exclude(status=BookingStatus.C)
            .annotate(y=ExtractYear("call_date"))
            .values("y")
            .annotate(c=Count("id"))
        }
        for idx, year in enumerate(calendar_years):
            bookings = bookings_by_year.get(year, 0)
            active = active_by_year.get(year) or {"calls": 0, "pax": 0}
            calls = int(active["calls"])
            pax = int(active["pax"])
            occ = occupancy_by_year[year]
            first_arrivals = first_arrivals_by_year.get(year, 0)
            conflicts = conflicts_by_year.get(year, 0)
            avg_pax = _avg_pax_per_call(calls, pax)
            prev_year = calendar_years[idx - 1] if idx > 0 else None
            prev_bookings = bookings_by_year.get(prev_year, 0) if prev_year else None
            prev_active = (
                active_by_year.get(prev_year) if prev_year is not None else None
            )
            prev_occ = occupancy_by_year.get(prev_year) if prev_year else None
            prev_avg_pax = (
                _avg_pax_per_call(
                    int(prev_active["calls"]),
                    int(prev_active["pax"]),
                )
                if prev_active is not None
                else None
            )
            by_year_kpis.append(
                {
                    "year": year,
                    "bookings": bookings,
                    "calls": calls,
                    "planned_pax": pax,
                    "avg_pax_per_call": avg_pax,
                    "occupancy_pct": occ["occupancy_pct"],
                    "occupied_slot_days": occ["occupied_slot_days"],
                    "capacity_slot_days": occ["capacity_slot_days"],
                    "first_arrivals": first_arrivals,
                    "conflicts": conflicts,
                    "bookings_yoy_pct": (
                        _delta_pct(bookings, prev_bookings)
                        if prev_bookings is not None
                        else None
                    ),
                    "pax_yoy_pct": (
                        _delta_pct(pax, int(prev_active["pax"]))
                        if prev_active is not None
                        else None
                    ),
                    "occupancy_yoy_pct": (
                        _delta_pct(
                            float(occ["occupancy_pct"]),
                            float(prev_occ["occupancy_pct"]),
                        )
                        if prev_occ is not None
                        else None
                    ),
                    "avg_pax_yoy_pct": (
                        _delta_pct(avg_pax, prev_avg_pax)
                        if prev_avg_pax is not None
                        else None
                    ),
                }
            )

    prior_occupancy_rows = iter_occupancy_booking_rows(
        prior_qs.filter(status__in=OCCUPANCY_STATUSES)
    )
    prior_occupied_slot_days, _ = occupied_physical_slot_days(prior_occupancy_rows)
    # Same pier plant × same window length → comparable occupancy rates.
    prior_occupancy_pct = (
        round((prior_occupied_slot_days / capacity_slot_days) * 100, 1)
        if capacity_slot_days > 0
        else 0.0
    )
    # --- Occupancy by port (period filter, physical pier slot-days) ---
    pier_by_port = {
        row["port_id"]: row["c"]
        for row in positions_qs.values("port_id").annotate(c=Count("id"))
    }
    occupancy_by_port = []
    for port in ports_in_scope.order_by("name"):
        pier_count = pier_by_port.get(port.id, 0)
        capacity = pier_count * day_count
        occupied = occupied_by_port_map.get(port.id, 0)
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

    occupancy_qs = qs.filter(status__in=OCCUPANCY_STATUSES)
    occupancy_trends = build_occupancy_trends(
        occupancy_qs=occupancy_qs,
        date_from=date_from,
        date_to=date_to,
        ports_in_scope=ports_in_scope,
        scoped_ports=scoped_ports or None,
        allowed_ports=allowed_ports,
    )
    by_port_month = build_by_port_month(active_qs, pax_basis=basis)

    years = sorted({date_from.year, date_to.year})

    return {
        "years": years,
        "year": years[0] if len(years) == 1 else None,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "day_count": day_count,
        "without_lta": without_lta,
        "pax_basis": basis,
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
            "avg_pax_per_call": avg_pax_per_call,
            "ports_count": ports_in_scope.count(),
            "first_arrivals": first_arrivals_count,
            "by_year": by_year_kpis,
        },
        "conflicts": _conflict_summary(qs),
        "pending_confirm": {
            "holds": holds_total,
            "lta": lta_total,
            "total": holds_total + lta_total,
            "hold_since": hold_since.isoformat() if hold_since else None,
            "lta_since": lta_since.isoformat() if lta_since else None,
            "by_port": pending_by_port,
        },
        "action_queue": {
            "as_of": today.isoformat(),
            "holds": holds_open.count(),
            "new_requests": nr_open.count(),
            "by_port": action_by_port,
        },
        "current_week": {
            "date_from": week_from.isoformat(),
            "date_to": week_to.isoformat(),
            "iso_week": iso_week,
            "total_confirmed": week_agg["calls"] or 0,
            "planned_pax": week_agg["planned_pax"] or 0,
            "by_port": week_by_port,
        },
        "peak_pax_by_port": peak_pax_by_port,
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
            "avg_pax_per_call": {
                "current": avg_pax_per_call,
                "prior": prior_avg_pax_per_call,
                "delta_pct": _delta_pct(avg_pax_per_call, prior_avg_pax_per_call),
            },
            "occupancy": {
                "current": occupancy_pct,
                "prior": prior_occupancy_pct,
                "delta_pct": _delta_pct(occupancy_pct, prior_occupancy_pct),
            },
        },
        "occupancy_by_port": occupancy_by_port,
        "occupancy_trends": occupancy_trends,
        "by_port_month": by_port_month,
        "by_shipping_line": [
            {
                "id": row["shipping_line_id"],
                "name": row["shipping_line__name"],
                "code": row["shipping_line__code"],
                "bookings": row["bookings"],
                "planned_pax": row["planned_pax"] or 0,
                "avg_planned_pax": row["avg_planned_pax"],
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
        "first_arrivals_by_port": [
            {
                "id": row["port_id"],
                "name": row["port__commercial_name"] or row["port__name"],
                "code": row["port__code"],
                "bookings": row["bookings"],
            }
            for row in first_arrivals_by_port_raw
        ],
        "by_cancellation_reason": by_cancellation_reason,
        "by_weekday": by_weekday,
        "status_breakdown": [
            {"status": "h", "label": "Hold", "count": hold},
            {"status": "co", "label": "Confirmadas", "count": confirmed},
            {"status": "cl", "label": "Confirmadas LTA", "count": confirmed_lta},
            {"status": "lta", "label": "LTA", "count": lta},
            {"status": "r", "label": "Real", "count": real},
            {"status": "c", "label": "Canceladas", "count": cancelled},
        ],
    }
