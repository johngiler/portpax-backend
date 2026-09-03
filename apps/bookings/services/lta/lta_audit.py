"""Snapshot / diff helpers for LTA agreement audit."""

from __future__ import annotations

from typing import Any

from apps.bookings.services.validation.legend_labels import (
    position_legend_label,
    vessel_legend_label,
)


def snapshot_lta(agreement) -> dict[str, Any]:
    port = getattr(agreement, "port", None)
    line = getattr(agreement, "shipping_line", None)
    vessels = list(agreement.vessels.all().order_by("name", "id"))
    positions = list(agreement.positions.select_related("port").order_by("code", "id"))
    vessel_ids = [v.pk for v in vessels]
    position_ids = [p.pk for p in positions]
    vessel_labels = [vessel_legend_label(v, fallback=f"#{v.pk}") for v in vessels]
    position_labels = [position_legend_label(p) for p in positions]
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
        "vessel_labels": vessel_labels,
        "position_ids": position_ids,
        "position_labels": position_labels,
        "weekdays": list(agreement.weekdays or []),
        "interval_days": agreement.interval_days,
        "cadence_anchor": (
            str(agreement.cadence_anchor) if agreement.cadence_anchor else None
        ),
        "date_exceptions": list(agreement.date_exceptions or []),
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


def _labeled_id_list_change(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    ids_key: str,
    labels_key: str,
) -> dict[str, Any] | None:
    before_ids = before.get(ids_key) or []
    after_ids = after.get(ids_key) or []
    if before_ids == after_ids:
        return None
    return {
        "from": before_ids,
        "to": after_ids,
        "from_labels": before.get(labels_key) or [],
        "to_labels": after.get(labels_key) or [],
    }


def _named_fk_change(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    id_key: str,
    code_key: str,
    name_key: str,
) -> dict[str, Any] | None:
    if before.get(id_key) == after.get(id_key):
        return None
    return {
        "from": before.get(id_key),
        "to": after.get(id_key),
        "from_code": before.get(code_key) or "",
        "to_code": after.get(code_key) or "",
        "from_name": before.get(name_key) or "",
        "to_name": after.get(name_key) or "",
    }


def diff_lta_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "code",
        "name",
        "all_vessels",
        "weekdays",
        "interval_days",
        "cadence_anchor",
        "date_exceptions",
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

    port_delta = _named_fk_change(
        before,
        after,
        id_key="port_id",
        code_key="port_code",
        name_key="port_name",
    )
    if port_delta is not None:
        changes["port_id"] = port_delta

    line_delta = _named_fk_change(
        before,
        after,
        id_key="shipping_line_id",
        code_key="shipping_line_code",
        name_key="shipping_line_name",
    )
    if line_delta is not None:
        changes["shipping_line_id"] = line_delta

    vessels_delta = _labeled_id_list_change(
        before,
        after,
        ids_key="vessel_ids",
        labels_key="vessel_labels",
    )
    if vessels_delta is not None:
        changes["vessel_ids"] = vessels_delta

    positions_delta = _labeled_id_list_change(
        before,
        after,
        ids_key="position_ids",
        labels_key="position_labels",
    )
    if positions_delta is not None:
        changes["position_ids"] = positions_delta

    return changes
