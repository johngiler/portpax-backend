from __future__ import annotations

from typing import Any

from apps.catalogs.models import (
    Berth,
    BerthImage,
    PortBollard,
    PortFender,
    PortImage,
    Position,
    PositionLoaRecalcRule,
    PositionNestingRule,
)
from apps.catalogs.services.port_catalog_audit.common import dec, port_context
from apps.catalogs.utils.position_code import position_short_code


def _position_inventory(position: Position) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bollards: list[dict[str, Any]] = []
    for line in position.bollard_lines.select_related("port_bollard").order_by("sort_order"):
        pb = line.port_bollard
        bollards.append(
            {
                "port_bollard_id": pb.pk,
                "capacity_t": pb.capacity_t,
                "bollard_type": pb.bollard_type,
                "label": pb.label or "",
                "quantity": line.quantity,
            }
        )
    fenders: list[dict[str, Any]] = []
    for line in position.fender_lines.select_related("port_fender").order_by("sort_order"):
        pf = line.port_fender
        fenders.append(
            {
                "port_fender_id": pf.pk,
                "fender_type": pf.fender_type,
                "quantity": line.quantity,
            }
        )
    return bollards, fenders


def snapshot_position(position: Position) -> dict[str, Any]:
    port = position.port
    berth = position.berth
    bollards, fenders = _position_inventory(position)
    return {
        "id": position.pk,
        **port_context(port),
        "code": position.code or "",
        "short_code": position_short_code(port.code, position.code),
        "position_type": position.position_type or "",
        "berth_id": position.berth_id,
        "berth_code": berth.code if berth else "",
        "max_loa_m": dec(position.max_loa_m),
        "min_loa_m": dec(position.min_loa_m),
        "max_beam_m": dec(position.max_beam_m),
        "min_draft_m": dec(position.min_draft_m),
        "min_eta": position.min_eta.isoformat() if position.min_eta else None,
        "bollard_count": position.bollard_count,
        "fender_count": position.fender_count,
        "bollard_allocations": bollards,
        "fender_allocations": fenders,
        "effective_from": str(position.effective_from) if position.effective_from else None,
        "effective_until": str(position.effective_until) if position.effective_until else None,
        "notes": position.notes or "",
        "latitude": dec(position.latitude),
        "longitude": dec(position.longitude),
        "sort_order": position.sort_order,
        "is_active": bool(position.is_active),
    }


def snapshot_berth(berth: Berth) -> dict[str, Any]:
    port = berth.port
    return {
        "id": berth.pk,
        **port_context(port),
        "code": berth.code or "",
        "name": berth.name or "",
        "length_m": dec(berth.length_m),
        "width_m": dec(berth.width_m),
        "walkway_length_m": dec(berth.walkway_length_m),
        "walkway_width_m": dec(berth.walkway_width_m),
        "min_draft_m": dec(berth.min_draft_m),
        "notes": berth.notes or "",
        "latitude": dec(berth.latitude),
        "longitude": dec(berth.longitude),
        "sort_order": berth.sort_order,
        "is_active": bool(berth.is_active),
    }


def snapshot_bollard(bollard: PortBollard) -> dict[str, Any]:
    port = bollard.port
    return {
        "id": bollard.pk,
        **port_context(port),
        "capacity_t": bollard.capacity_t,
        "bollard_type": bollard.bollard_type or "",
        "quantity": bollard.quantity,
        "label": bollard.label or "",
        "sort_order": bollard.sort_order,
        "notes": bollard.notes or "",
        "is_active": bool(bollard.is_active),
    }


def snapshot_fender(fender: PortFender) -> dict[str, Any]:
    port = fender.port
    return {
        "id": fender.pk,
        **port_context(port),
        "fender_type": fender.fender_type or "",
        "quantity": fender.quantity,
        "sort_order": fender.sort_order,
        "notes": fender.notes or "",
        "is_active": bool(fender.is_active),
    }


def snapshot_port_image(image: PortImage) -> dict[str, Any]:
    port = image.port
    return {
        "id": image.pk,
        **port_context(port),
        "caption": image.caption or "",
        "sort_order": image.sort_order,
        "is_cover": bool(image.is_cover),
        "has_image": bool(image.image),
    }


def snapshot_berth_image(image: BerthImage) -> dict[str, Any]:
    berth = image.berth
    port = berth.port
    return {
        "id": image.pk,
        **port_context(port),
        "berth_id": berth.pk,
        "berth_code": berth.code or "",
        "caption": image.caption or "",
        "sort_order": image.sort_order,
        "is_cover": bool(image.is_cover),
        "has_image": bool(image.image),
    }


def snapshot_position_image(image) -> dict[str, Any]:
    position = image.position
    port = position.port
    return {
        "id": image.pk,
        **port_context(port),
        "position_id": position.pk,
        "position_short_code": position_short_code(port.code, position.code),
        "caption": image.caption or "",
        "sort_order": image.sort_order,
        "is_cover": bool(image.is_cover),
        "has_image": bool(image.image),
    }


def snapshot_nesting_rule(rule: PositionNestingRule) -> dict[str, Any]:
    port = rule.port
    return {
        "id": rule.pk,
        **port_context(port),
        "outer_position_id": rule.outer_position_id,
        "outer_position_code": position_short_code(port.code, rule.outer_position.code),
        "inner_position_id": rule.inner_position_id,
        "inner_position_code": position_short_code(port.code, rule.inner_position.code),
        "enforce_eta": bool(rule.enforce_eta),
        "enforce_etd": bool(rule.enforce_etd),
        "is_active": bool(rule.is_active),
        "notes": rule.notes or "",
    }


def snapshot_loa_recalc_rule(rule: PositionLoaRecalcRule) -> dict[str, Any]:
    port = rule.port
    return {
        "id": rule.pk,
        **port_context(port),
        "position_a_id": rule.position_a_id,
        "position_a_code": position_short_code(port.code, rule.position_a.code),
        "position_b_id": rule.position_b_id,
        "position_b_code": position_short_code(port.code, rule.position_b.code),
        "max_loa_m": dec(rule.max_loa_m),
        "separation_m": dec(rule.separation_m),
        "yellow_from_m": dec(rule.yellow_from_m),
        "red_from_m": dec(rule.red_from_m),
        "is_active": bool(rule.is_active),
        "notes": rule.notes or "",
    }
