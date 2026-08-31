from __future__ import annotations

from typing import Any

from apps.catalogs.services.port_catalog_audit.common import field_change


def _dec(value) -> float | None:
    if value is None:
        return None
    return float(value)


def snapshot_vessel(vessel) -> dict[str, Any]:
    line = vessel.shipping_line
    group = getattr(line, "group", None)
    return {
        "id": vessel.pk,
        "shipping_line_id": vessel.shipping_line_id,
        "shipping_line_code": line.code or "",
        "shipping_line_name": line.name or "",
        "group_name": getattr(group, "name", "") or "",
        "name": vessel.name or "",
        "ship_code": vessel.ship_code or "",
        "vessel_class": vessel.vessel_class or "",
        "gross_tonnage": _dec(vessel.gross_tonnage),
        "pax_capacity": vessel.pax_capacity,
        "crew_capacity": vessel.crew_capacity,
        "loa_m": _dec(vessel.loa_m),
        "beam_m": _dec(vessel.beam_m),
        "draft_m": _dec(vessel.draft_m),
        "flag": vessel.flag or "",
        "year_built": vessel.year_built,
        "segment": vessel.segment or "",
        "size_category": vessel.size_category or "",
        "mooring_line_count": vessel.mooring_line_count,
        "bollard_count": vessel.bollard_count,
        "bollard_swl_t": _dec(vessel.bollard_swl_t),
        "is_active": bool(vessel.is_active),
        "has_logo": bool(vessel.logo),
    }


def vessel_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "vessel",
        "vessel_name": snap.get("name") or "",
        "name": snap.get("name") or "",
        "shipping_line_code": snap.get("shipping_line_code") or "",
        "shipping_line_name": snap.get("shipping_line_name") or "",
    }


def diff_vessel_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "name",
        "ship_code",
        "vessel_class",
        "gross_tonnage",
        "pax_capacity",
        "crew_capacity",
        "loa_m",
        "beam_m",
        "draft_m",
        "flag",
        "year_built",
        "segment",
        "size_category",
        "mooring_line_count",
        "bollard_count",
        "bollard_swl_t",
        "is_active",
        "has_logo",
    ):
        delta = field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    return changes
