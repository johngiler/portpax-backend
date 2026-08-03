from __future__ import annotations

from typing import Any


def _dec(value) -> float | None:
    if value is None:
        return None
    return float(value)


def snapshot_port(port) -> dict[str, Any]:
    return {
        "id": port.pk,
        "code": port.code or "",
        "name": port.name or "",
        "commercial_name": port.commercial_name or "",
        "country": port.country or "",
        "region": port.region or "",
        "latitude": _dec(port.latitude),
        "longitude": _dec(port.longitude),
        "status": port.status or "",
        "min_berth_draft_m": _dec(port.min_berth_draft_m),
        "anchorage_slot_count": port.anchorage_slot_count,
        "fender_count": port.fender_count,
        "notes": port.notes or "",
        "is_active": bool(port.is_active),
        "has_logo": bool(port.logo),
    }


def _field_change(before: Any, after: Any) -> dict[str, Any] | None:
    if before == after:
        return None
    return {"from": before, "to": after}


def diff_port_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "code",
        "name",
        "commercial_name",
        "country",
        "region",
        "latitude",
        "longitude",
        "status",
        "min_berth_draft_m",
        "anchorage_slot_count",
        "fender_count",
        "notes",
        "is_active",
        "has_logo",
    ):
        delta = _field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    return changes
