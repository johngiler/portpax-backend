"""Enrich audit `changes` so history UI never shows bare catalog IDs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from apps.bookings.services.validation.legend_labels import (
    position_legend_label,
    vessel_legend_label,
)
from apps.catalogs.models import Port, Position, Vessel


def _as_int_list(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            return None
    return out


def _has_labels(change: dict[str, Any]) -> bool:
    return (
        isinstance(change.get("from_labels"), list)
        and isinstance(change.get("to_labels"), list)
    )


def enrich_id_list_change(
    change: Any,
    *,
    resolve: Callable[[list[int]], list[str]],
) -> Any:
    """Attach from_labels / to_labels on a {from,to} id-list delta when missing."""
    if not isinstance(change, dict):
        return change
    if _has_labels(change):
        return change
    from_ids = _as_int_list(change.get("from", change.get("old")))
    to_ids = _as_int_list(change.get("to", change.get("new")))
    if from_ids is None and to_ids is None:
        return change
    out = dict(change)
    if from_ids is not None and "from_labels" not in out:
        out["from_labels"] = resolve(from_ids)
    if to_ids is not None and "to_labels" not in out:
        out["to_labels"] = resolve(to_ids)
    return out


def _position_labels(ids: list[int]) -> list[str]:
    if not ids:
        return []
    rows = Position.objects.filter(pk__in=ids).select_related("port")
    by_id = {p.pk: position_legend_label(p) for p in rows}
    return [by_id.get(i, f"#{i}") for i in ids]


def _vessel_labels(ids: list[int]) -> list[str]:
    if not ids:
        return []
    rows = Vessel.objects.filter(pk__in=ids)
    by_id = {v.pk: vessel_legend_label(v, fallback=f"#{v.pk}") for v in rows}
    return [by_id.get(i, f"#{i}") for i in ids]


def _port_labels(ids: list[int]) -> list[str]:
    if not ids:
        return []
    rows = Port.objects.filter(pk__in=ids)
    by_id = {
        p.pk: (p.name or p.code or f"#{p.pk}").strip() or f"#{p.pk}" for p in rows
    }
    return [by_id.get(i, f"#{i}") for i in ids]


def enrich_named_fk_change(
    change: Any,
    *,
    resolve_one: Callable[[int], tuple[str, str]],
) -> Any:
    """Attach from_code/to_code and from_name/to_name for a single FK id delta."""
    if not isinstance(change, dict):
        return change
    if change.get("from_name") or change.get("to_name") or change.get("from_code"):
        return change
    out = dict(change)
    raw_from = out.get("from", out.get("old"))
    raw_to = out.get("to", out.get("new"))
    try:
        if raw_from is not None and raw_from != "":
            code, name = resolve_one(int(raw_from))
            out.setdefault("from_code", code)
            out.setdefault("from_name", name)
        if raw_to is not None and raw_to != "":
            code, name = resolve_one(int(raw_to))
            out.setdefault("to_code", code)
            out.setdefault("to_name", name)
    except (TypeError, ValueError):
        return change
    return out


def _port_code_name(pk: int) -> tuple[str, str]:
    port = Port.objects.filter(pk=pk).first()
    if port is None:
        return ("", f"#{pk}")
    return (port.code or "", port.name or port.code or f"#{pk}")


def _line_code_name(pk: int) -> tuple[str, str]:
    from apps.catalogs.models import ShippingLine

    line = ShippingLine.objects.filter(pk=pk).first()
    if line is None:
        return ("", f"#{pk}")
    return (line.code or "", line.name or line.code or f"#{pk}")


def enrich_lta_audit_changes(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    if not changes or not isinstance(changes, dict):
        return changes
    out = deepcopy(changes)
    if "position_ids" in out:
        out["position_ids"] = enrich_id_list_change(
            out["position_ids"],
            resolve=_position_labels,
        )
    if "vessel_ids" in out:
        out["vessel_ids"] = enrich_id_list_change(
            out["vessel_ids"],
            resolve=_vessel_labels,
        )
    if "port_id" in out:
        out["port_id"] = enrich_named_fk_change(
            out["port_id"],
            resolve_one=_port_code_name,
        )
    if "shipping_line_id" in out:
        out["shipping_line_id"] = enrich_named_fk_change(
            out["shipping_line_id"],
            resolve_one=_line_code_name,
        )
    return out


def enrich_user_audit_changes(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    if not changes or not isinstance(changes, dict):
        return changes
    out = deepcopy(changes)
    if "port_ids" in out:
        out["port_ids"] = enrich_id_list_change(
            out["port_ids"],
            resolve=_port_labels,
        )
    return out


def enrich_shipping_line_audit_changes(
    changes: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not changes or not isinstance(changes, dict):
        return changes
    out = deepcopy(changes)
    group_id = out.get("group_id")
    if isinstance(group_id, dict) and not (
        group_id.get("from_name") or group_id.get("to_name")
    ):
        from apps.catalogs.models import ShippingLineGroup

        def _group_name(pk: int) -> tuple[str, str]:
            g = ShippingLineGroup.objects.filter(pk=pk).first()
            if g is None:
                return ("", f"#{pk}")
            return ("", g.name or f"#{pk}")

        out["group_id"] = enrich_named_fk_change(
            group_id,
            resolve_one=_group_name,
        )
        # Prefer single friendly chip; drop redundant group_name delta.
        if "group_name" in out:
            del out["group_name"]
    return out
