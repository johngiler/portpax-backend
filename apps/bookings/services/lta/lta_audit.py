"""Snapshot / diff helpers for LTA agreement audit."""

from __future__ import annotations

from typing import Any


def snapshot_lta(agreement) -> dict[str, Any]:
    port = getattr(agreement, "port", None)
    line = getattr(agreement, "shipping_line", None)
    vessel_ids = sorted(agreement.vessels.values_list("id", flat=True))
    position_ids = sorted(agreement.positions.values_list("id", flat=True))
    return {
        "id": agreement.pk,
        "code": agreement.code or "",
        "name": agreement.name or "",
        "port_id": agreement.port_id,
        "port_code": getattr(port, "code", "") or "",
        "port_name": getattr(port, "name", "") or "",
        "shipping_line_id": agreement.shipping_line_id,
        "shipping_line_code": getattr(line, "code", "") or "",
        "shipping_line_name": getattr(line, "name", "") or "",
        "all_vessels": bool(agreement.all_vessels),
        "vessel_ids": vessel_ids,
        "position_ids": position_ids,
        "weekdays": list(agreement.weekdays or []),
        "interval_days": agreement.interval_days,
        "cadence_anchor": (
            str(agreement.cadence_anchor) if agreement.cadence_anchor else None
        ),
        "min_packs": agreement.min_packs,
        "advance_months_min": agreement.advance_months_min,
        "advance_months_max": agreement.advance_months_max,
        "booking_policy": agreement.booking_policy,
        "lta_depth_blocks": agreement.lta_depth_blocks,
        "reserve_foreign_slots": bool(agreement.reserve_foreign_slots),
        "valid_from": str(agreement.valid_from) if agreement.valid_from else None,
        "valid_until": str(agreement.valid_until) if agreement.valid_until else None,
        "is_active": bool(agreement.is_active),
        "notes": agreement.notes or "",
        "has_contract": bool(agreement.contract_file),
    }


def _field_change(before: Any, after: Any) -> dict[str, Any] | None:
    if before == after:
        return None
    return {"from": before, "to": after}


def diff_lta_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "code",
        "name",
        "port_id",
        "port_code",
        "shipping_line_id",
        "shipping_line_code",
        "all_vessels",
        "vessel_ids",
        "position_ids",
        "weekdays",
        "interval_days",
        "cadence_anchor",
        "min_packs",
        "advance_months_min",
        "advance_months_max",
        "booking_policy",
        "lta_depth_blocks",
        "reserve_foreign_slots",
        "valid_from",
        "valid_until",
        "is_active",
        "notes",
        "has_contract",
    ):
        delta = _field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    return changes
