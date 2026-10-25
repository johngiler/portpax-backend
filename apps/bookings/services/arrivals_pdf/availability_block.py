"""Continuous availability blocks: one port × full date range (not split by month)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from apps.bookings.services.arrivals_pdf.occupancy import (
    days_in_range,
    prepare_availability_layout,
)


@dataclass(frozen=True)
class AvailabilityPortBlock:
    port: object
    labels: list[str]
    pos_index: dict[int, int]
    counts: list[int]
    occupied: dict[date, list]
    days: list[date]

    @property
    def col_count(self) -> int:
        return 2 + max(len(self.labels), 1)


def resolve_export_ports(
    *,
    port_id: int | None = None,
    port_ids: list[int] | None = None,
    allowed_ports: set[int] | None = None,
) -> list:
    from apps.catalogs.models import Port

    requested: list[int] = []
    for value in port_ids or []:
        if value and value not in requested:
            requested.append(value)
    if port_id and port_id not in requested:
        requested.append(port_id)

    qs = Port.objects.all().order_by("name")
    if allowed_ports is not None:
        qs = qs.filter(pk__in=allowed_ports)
    if requested:
        qs = qs.filter(pk__in=requested)
        ports = list(qs)
        found = {port.id for port in ports}
        missing = [pid for pid in requested if pid not in found]
        if missing:
            raise ValueError("Puerto no permitido.")
        return ports
    return list(qs)


def build_port_blocks(
    bookings: list,
    ports: list,
    date_from: date,
    date_to: date,
) -> list[AvailabilityPortBlock]:
    by_port: dict[int, list] = defaultdict(list)
    for booking in bookings:
        by_port[booking.port_id].append(booking)
    days = days_in_range(date_from, date_to)
    blocks: list[AvailabilityPortBlock] = []
    for port in ports:
        rows = by_port.get(port.id, [])
        labels, pos_index, counts = prepare_availability_layout(port, rows)
        occupied: dict[date, list] = defaultdict(list)
        for booking in rows:
            occupied[booking.call_date].append(booking)
        blocks.append(
            AvailabilityPortBlock(
                port=port,
                labels=labels,
                pos_index=pos_index,
                counts=counts,
                occupied=occupied,
                days=days,
            )
        )
    return blocks
