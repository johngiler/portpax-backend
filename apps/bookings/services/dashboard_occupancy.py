"""Physical pier slot-day occupancy for the Dashboard KPI.

Capacity = active atomic pier positions × days in range (combined catalog
rows like E1+E2 are excluded — they are not bookable capacity).

Occupied = distinct (position_id, call_date) after expanding each booking:
- Combined slot → its source piers (legacy mega booking on E1+E2).
- Physical pier with vessel LOA ≥ combined min_loa of its pair → all source
  piers of that pair (mega on E1 or E2 spans both).
- Otherwise, if vessel LOA exceeds that slot's max_loa_m and has an active
  LOA-recalc sibling → self + sibling (shared-wall overflow).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from django.db.models import QuerySet

from apps.catalogs.models import (
    Position,
    PositionComponent,
    PositionLoaRecalcRule,
    PositionType,
)
from apps.catalogs.services.position_combination import exclude_combined_positions


def atomic_pier_positions_qs(
    *,
    port_id: int | None = None,
    port_ids: list[int] | None = None,
    allowed_ports: list[int] | None = None,
) -> QuerySet[Position]:
    qs = Position.objects.filter(
        is_active=True,
        position_type=PositionType.PIER,
        port__is_active=True,
    )
    qs = exclude_combined_positions(qs)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_ids:
        qs = qs.filter(port_id__in=port_ids)
    elif port_id:
        qs = qs.filter(port_id=port_id)
    return qs


def _combined_sources() -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    for combined_id, source_id in PositionComponent.objects.values_list(
        "combined_position_id", "source_position_id"
    ):
        mapping.setdefault(combined_id, []).append(source_id)
    return mapping


def _source_to_combined_mega() -> dict[int, tuple[int, Decimal]]:
    """
    source_pier_id → (combined_id, min_loa_m) for mega thresholds.

    Includes inactive combined rows: they still define when a ship on E1/E2
    historically spans both physical piers.
    """
    mapping: dict[int, tuple[int, Decimal]] = {}
    rows = PositionComponent.objects.values_list(
        "source_position_id",
        "combined_position_id",
        "combined_position__min_loa_m",
    )
    for source_id, combined_id, min_loa in rows:
        if min_loa is None:
            continue
        mapping[source_id] = (combined_id, Decimal(str(min_loa)))
    return mapping

def _loa_siblings() -> dict[int, int]:
    """position_id → sibling_id for active shared-pier LOA rules."""
    siblings: dict[int, int] = {}
    for a_id, b_id in PositionLoaRecalcRule.objects.filter(is_active=True).values_list(
        "position_a_id", "position_b_id"
    ):
        siblings[a_id] = b_id
        siblings[b_id] = a_id
    return siblings


def _slot_max_loa() -> dict[int, Decimal]:
    rows = Position.objects.filter(max_loa_m__isnull=False).values_list(
        "id", "max_loa_m"
    )
    return {pid: Decimal(str(max_loa)) for pid, max_loa in rows}


def _expand_booking_positions(
    *,
    position_id: int,
    vessel_loa: Decimal | None,
    combined_sources: dict[int, list[int]],
    source_to_mega: dict[int, tuple[int, Decimal]],
    loa_siblings: dict[int, int],
    slot_max_loa: dict[int, Decimal],
) -> set[int]:
    sources = combined_sources.get(position_id)
    if sources:
        return set(sources)

    occupied = {position_id}

    # Mega on a physical pier that belongs to a combined pair (e.g. E1/E2).
    mega = source_to_mega.get(position_id)
    if mega is not None and vessel_loa is not None and vessel_loa >= mega[1]:
        pair_sources = combined_sources.get(mega[0])
        if pair_sources:
            occupied.update(pair_sources)
            return occupied

    # Soft slot overflow into shared-pier sibling (LOA recalc).
    sibling_id = loa_siblings.get(position_id)
    slot_max = slot_max_loa.get(position_id)
    if (
        sibling_id is not None
        and slot_max is not None
        and vessel_loa is not None
        and vessel_loa > slot_max
    ):
        occupied.add(sibling_id)
    return occupied


def occupied_physical_slot_days(
    bookings: Iterable[tuple[int | None, date, int | None, Decimal | None]],
    *,
    port_ids: set[int] | None = None,
) -> tuple[int, dict[int, int]]:
    """
    Count distinct physical (position, call_date) slot-days.

    `bookings` yields (position_id, call_date, port_id, vessel_loa_m).
    Returns (total, occupied_by_port_id).
    """
    rows = list(bookings)
    combined_sources = _combined_sources()
    source_to_mega = _source_to_combined_mega()
    loa_siblings = _loa_siblings()
    slot_max_loa = _slot_max_loa()

    needed_ids = {pid for pid, _, _, _ in rows if pid is not None}
    needed_ids.update(combined_sources.keys())
    for sources in combined_sources.values():
        needed_ids.update(sources)
    needed_ids.update(loa_siblings.keys())
    needed_ids.update(loa_siblings.values())

    position_port = dict(
        Position.objects.filter(pk__in=needed_ids).values_list("id", "port_id")
    )

    keys: set[tuple[int, date]] = set()
    by_port: dict[int, set[tuple[int, date]]] = {}

    for position_id, call_date, booking_port_id, vessel_loa in rows:
        if position_id is None or call_date is None:
            continue
        physical_ids = _expand_booking_positions(
            position_id=position_id,
            vessel_loa=vessel_loa,
            combined_sources=combined_sources,
            source_to_mega=source_to_mega,
            loa_siblings=loa_siblings,
            slot_max_loa=slot_max_loa,
        )
        for pid in physical_ids:
            port_id = position_port.get(pid, booking_port_id)
            if port_id is None:
                continue
            if port_ids is not None and port_id not in port_ids:
                continue
            key = (pid, call_date)
            keys.add(key)
            by_port.setdefault(port_id, set()).add(key)

    return len(keys), {pid: len(slots) for pid, slots in by_port.items()}

def iter_occupancy_booking_rows(qs: QuerySet) -> list[tuple[int | None, date, int | None, Decimal | None]]:
    rows: list[tuple[int | None, date, int | None, Decimal | None]] = []
    for position_id, call_date, port_id, loa in qs.values_list(
        "position_id",
        "call_date",
        "port_id",
        "vessel__loa_m",
    ):
        loa_dec = Decimal(str(loa)) if loa is not None else None
        rows.append((position_id, call_date, port_id, loa_dec))
    return rows
