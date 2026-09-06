"""Enrich audit `changes` so history UI never shows bare catalog IDs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from apps.bookings.services.validation.legend_labels import (
    position_legend_label,
    vessel_legend_label,
)
from apps.catalogs.models import Berth, Port, Position, Vessel
from apps.catalogs.models.port import PortOperationalStatus
from apps.catalogs.models.position import PositionType
from apps.catalogs.utils.position_code import position_short_code

PORT_STATUS_LABELS = {
    PortOperationalStatus.OPERATIONAL: "Operativo",
    PortOperationalStatus.IN_DEVELOPMENT: "En desarrollo",
    PortOperationalStatus.PLANNED_EXTENSION: "Ampliación proyectada",
}

POSITION_TYPE_LABELS = {
    PositionType.PIER: "Muelle",
    PositionType.ANCHORAGE: "Fondeo",
}

BOLLARD_TYPE_LABELS = {
    "standard": "Estándar",
    "t_head": "T-head",
    "quick_release": "Quick release",
    "single_bitt": "Single bitt",
    "other": "Otro",
}


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
    """Attach from_code/to_code and from_name/to_name for a single FK id delta.

    Fills each side independently. Explicit ``None`` / empty codes are missing.
    """
    if not isinstance(change, dict):
        return change
    out = dict(change)
    raw_from = out.get("from", out.get("old"))
    raw_to = out.get("to", out.get("new"))

    def _blank(value: Any) -> bool:
        return value is None or value == ""

    def _fill(raw: Any, code_key: str, name_key: str) -> None:
        if raw is None or raw == "":
            return
        need_code = _blank(out.get(code_key))
        need_name = _blank(out.get(name_key))
        if not need_code and not need_name:
            return
        code, name = resolve_one(int(raw))
        if need_code:
            out[code_key] = code
        if need_name:
            out[name_key] = name

    try:
        _fill(raw_from, "from_code", "from_name")
        _fill(raw_to, "to_code", "to_name")
    except (TypeError, ValueError):
        return change
    return out


def _shorten_position_code(code: Any) -> str:
    if not isinstance(code, str):
        return ""
    text = code.strip()
    if not text:
        return ""
    # Legacy audits may store full catalog code "{port}-{short}".
    if "-" in text:
        return text.split("-", 1)[1] or text
    return text


def _normalize_position_codes(change: Any) -> Any:
    """Ensure position sides resolve to short labels (E1), never bare PKs."""
    if not isinstance(change, dict):
        return change
    out = enrich_named_fk_change(change, resolve_one=_position_code_name)
    if not isinstance(out, dict):
        return change
    for key in ("from_code", "to_code"):
        shortened = _shorten_position_code(out.get(key))
        if shortened:
            out[key] = shortened
    return out


BOOKING_STATUS_LABELS = {
    "nr": "Solicitada",
    "h": "En evaluación",
    "co": "Confirmada",
    "cl": "Confirmada LTA",
    "lta": "LTA",
    "ltd": "Long Term Deployment",
    "r": "Real",
    "c": "Cancelada",
}


def _vessel_code_name(pk: int) -> tuple[str, str]:
    vessel = Vessel.objects.filter(pk=pk).first()
    if vessel is None:
        return ("", f"#{pk}")
    name = vessel_legend_label(vessel, fallback=f"#{pk}")
    return ("", name)


def _lta_code_name(pk: int) -> tuple[str, str]:
    from apps.bookings.models import LongTermAgreement

    agreement = LongTermAgreement.objects.filter(pk=pk).first()
    if agreement is None:
        return ("", f"#{pk}")
    code = agreement.code or f"#{pk}"
    return (code, code)


def enrich_booking_audit_changes(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    """Booking history must never paint raw FKs / PKs to operators."""
    if not changes or not isinstance(changes, dict):
        return changes
    out = deepcopy(changes)
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
    if "vessel_id" in out:
        out["vessel_id"] = enrich_named_fk_change(
            out["vessel_id"],
            resolve_one=_vessel_code_name,
        )
    if "position_id" in out:
        out["position_id"] = _normalize_position_codes(out["position_id"])
    if "long_term_agreement_id" in out:
        out["long_term_agreement_id"] = enrich_named_fk_change(
            out["long_term_agreement_id"],
            resolve_one=_lta_code_name,
        )
    if "status" in out:
        out["status"] = enrich_choice_change(out["status"], BOOKING_STATUS_LABELS)
    return out


def _port_code_name(pk: int) -> tuple[str, str]:
    port = Port.objects.filter(pk=pk).first()
    if port is None:
        return ("", f"#{pk}")
    return (port.code or "", port.name or port.code or f"#{pk}")


def enrich_choice_change(change: Any, labels: dict[str, str]) -> Any:
    """Attach from_label / to_label for enum-like {from,to} deltas."""
    if not isinstance(change, dict):
        return change
    out = dict(change)
    for side, label_key in (("from", "from_label"), ("to", "to_label")):
        raw = out.get(side, out.get("old" if side == "from" else "new"))
        if isinstance(raw, str) and raw in labels:
            out.setdefault(label_key, labels[raw])
    return out


def _berth_code_name(pk: int) -> tuple[str, str]:
    berth = Berth.objects.filter(pk=pk).select_related("port").first()
    if berth is None:
        return ("", f"#{pk}")
    code = position_short_code(berth.port.code, berth.code) if berth.port_id else berth.code
    name = berth.name or code or f"#{pk}"
    return (code or "", name)


def _position_code_name(pk: int) -> tuple[str, str]:
    position = Position.objects.filter(pk=pk).select_related("port").first()
    if position is None:
        return ("", f"#{pk}")
    code = position_short_code(position.port.code, position.code)
    return (code, code)


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
    if "is_active" in out and isinstance(out["is_active"], dict):
        active = dict(out["is_active"])
        for side, label_key in (("from", "from_label"), ("to", "to_label")):
            raw = active.get(side, active.get("old" if side == "from" else "new"))
            if isinstance(raw, bool):
                active.setdefault(label_key, "Activo" if raw else "Inactivo")
        out["is_active"] = active
    return out


def enrich_port_audit_changes(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    if not changes or not isinstance(changes, dict):
        return changes
    out = deepcopy(changes)
    if "status" in out:
        out["status"] = enrich_choice_change(out["status"], PORT_STATUS_LABELS)
    if "position_type" in out:
        out["position_type"] = enrich_choice_change(
            out["position_type"],
            POSITION_TYPE_LABELS,
        )
    if "bollard_type" in out:
        out["bollard_type"] = enrich_choice_change(
            out["bollard_type"],
            BOLLARD_TYPE_LABELS,
        )
    for key, resolver in (
        ("berth_id", _berth_code_name),
        ("outer_position_id", _position_code_name),
        ("inner_position_id", _position_code_name),
        ("position_a_id", _position_code_name),
        ("position_b_id", _position_code_name),
    ):
        if key in out:
            out[key] = enrich_named_fk_change(out[key], resolve_one=resolver)
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
