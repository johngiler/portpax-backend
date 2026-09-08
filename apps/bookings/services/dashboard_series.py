"""Dashboard series: passengers/calls by port×month and occupancy trends."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from django.db.models import Count, QuerySet, Sum
from django.db.models.functions import Coalesce

from apps.bookings.services.dashboard_occupancy import (
    atomic_pier_positions_qs,
    iter_occupancy_booking_rows,
    occupied_physical_slot_days,
    occupied_physical_slots,
)
from apps.bookings.services.lta.windows import SeasonKind, block_containing
from apps.catalogs.models import Port
from apps.catalogs.utils.position_code import position_short_code


def _port_label(row: dict) -> str:
    return row.get("port__commercial_name") or row["port__name"]


def _iter_month_slices(date_from: date, date_to: date):
    y, m = date_from.year, date_from.month
    while True:
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        slice_from = max(start, date_from)
        slice_to = min(end, date_to)
        if slice_from <= slice_to:
            yield y, m, slice_from, slice_to
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        if date(y, m, 1) > date_to:
            break


def _iter_season_slices(date_from: date, date_to: date):
    cursor = date_from
    while cursor <= date_to:
        kind, start, end = block_containing(cursor)
        slice_from = max(start, date_from)
        slice_to = min(end, date_to)
        if kind == SeasonKind.SUMMER:
            label = f"Verano {start.year}"
        else:
            label = f"Invierno {start.year}/{end.year}"
        yield kind.value, label, slice_from, slice_to
        cursor = slice_to + timedelta(days=1)


def build_by_port_month(active_qs: QuerySet, *, limit_ports: int = 8) -> dict:
    """
    Calls + planned passengers per port × calendar month (1–12) in scoped qs.
    Top ports by total calls.
    """
    rows = (
        active_qs.values(
            "port_id",
            "port__name",
            "port__code",
            "port__commercial_name",
            "call_date__month",
        )
        .annotate(
            calls=Count("id"),
            passengers=Coalesce(Sum("planned_pax"), 0),
        )
        .order_by("port_id", "call_date__month")
    )

    by_port: dict[int, dict] = {}
    for row in rows:
        pid = row["port_id"]
        entry = by_port.get(pid)
        if entry is None:
            entry = {
                "port_id": pid,
                "name": _port_label(row),
                "code": row["port__code"],
                "months": {
                    m: {"calls": 0, "passengers": 0} for m in range(1, 13)
                },
                "_total_calls": 0,
            }
            by_port[pid] = entry
        month = row["call_date__month"]
        calls = int(row["calls"] or 0)
        pax = int(row["passengers"] or 0)
        entry["months"][month] = {"calls": calls, "passengers": pax}
        entry["_total_calls"] += calls

    ranked = sorted(
        by_port.values(),
        key=lambda e: e["_total_calls"],
        reverse=True,
    )[:limit_ports]

    ports = []
    for entry in ranked:
        entry.pop("_total_calls", None)
        months = [
            {
                "month": m,
                "calls": entry["months"][m]["calls"],
                "passengers": entry["months"][m]["passengers"],
            }
            for m in range(1, 13)
        ]
        ports.append(
            {
                "port_id": entry["port_id"],
                "name": entry["name"],
                "code": entry["code"],
                "months": months,
            }
        )

    return {"ports": ports}


def _occupancy_for_slice(
    *,
    occupancy_qs: QuerySet,
    slice_from: date,
    slice_to: date,
    pier_by_port: dict[int, int],
    ports: list[Port],
) -> list[dict]:
    day_count = (slice_to - slice_from).days + 1
    rows = iter_occupancy_booking_rows(
        occupancy_qs.filter(call_date__gte=slice_from, call_date__lte=slice_to)
    )
    _, occupied_by_port = occupied_physical_slot_days(rows)
    out = []
    for port in ports:
        pier_count = pier_by_port.get(port.id, 0)
        capacity = pier_count * day_count
        occupied = occupied_by_port.get(port.id, 0)
        out.append(
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
    out.sort(key=lambda r: r["occupancy_pct"], reverse=True)
    return out


def build_occupancy_trends(
    *,
    occupancy_qs: QuerySet,
    date_from: date,
    date_to: date,
    ports_in_scope: QuerySet,
    scoped_ports: list[int] | None,
    allowed_ports: list[int] | None,
) -> dict:
    ports = list(ports_in_scope.order_by("name"))
    pier_by_port = {
        row["port_id"]: row["c"]
        for row in atomic_pier_positions_qs(
            port_ids=scoped_ports or None,
            allowed_ports=allowed_ports,
        )
        .values("port_id")
        .annotate(c=Count("id"))
    }

    by_month = []
    for year, month, slice_from, slice_to in _iter_month_slices(date_from, date_to):
        by_month.append(
            {
                "year": year,
                "month": month,
                "date_from": slice_from.isoformat(),
                "date_to": slice_to.isoformat(),
                "by_port": _occupancy_for_slice(
                    occupancy_qs=occupancy_qs,
                    slice_from=slice_from,
                    slice_to=slice_to,
                    pier_by_port=pier_by_port,
                    ports=ports,
                ),
            }
        )

    by_season = []
    for kind, label, slice_from, slice_to in _iter_season_slices(date_from, date_to):
        by_season.append(
            {
                "season": kind,
                "label": label,
                "date_from": slice_from.isoformat(),
                "date_to": slice_to.isoformat(),
                "by_port": _occupancy_for_slice(
                    occupancy_qs=occupancy_qs,
                    slice_from=slice_from,
                    slice_to=slice_to,
                    pier_by_port=pier_by_port,
                    ports=ports,
                ),
            }
        )

    day_count = (date_to - date_from).days + 1
    positions = list(
        atomic_pier_positions_qs(
            port_ids=scoped_ports or None,
            allowed_ports=allowed_ports,
        )
        .select_related("port")
        .order_by("port__name", "code")
    )
    rows = iter_occupancy_booking_rows(
        occupancy_qs.filter(call_date__gte=date_from, call_date__lte=date_to)
    )
    _, _, by_position = occupied_physical_slots(rows)
    by_dock = []
    for pos in positions:
        occupied = by_position.get(pos.id, 0)
        capacity = day_count
        by_dock.append(
            {
                "position_id": pos.id,
                "port_id": pos.port_id,
                "port_name": pos.port.commercial_name or pos.port.name,
                "code": position_short_code(pos.port.code, pos.code),
                "capacity_slot_days": capacity,
                "occupied_slot_days": occupied,
                "occupancy_pct": (
                    round((occupied / capacity) * 100, 1) if capacity > 0 else 0.0
                ),
            }
        )
    by_dock.sort(key=lambda r: r["occupancy_pct"], reverse=True)

    return {
        "by_month": by_month,
        "by_season": by_season,
        "by_dock": by_dock,
    }
