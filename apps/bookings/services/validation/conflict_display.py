"""Conflict chips and card highlight hints for API payloads."""

from __future__ import annotations

from apps.bookings.services.validation.conflict_codes import (
    CONFLICT_SEVERITY_BY_CODE,
    resolve_issue_severity,
)
from apps.bookings.services.validation.conflict_type_filters import (
    CONFLICT_TYPES,
    snapshot_has_conflict_type,
)
from apps.bookings.services.validation.conflicts import max_snapshot_severity

CONFLICT_HIGHLIGHT_BY_CODE: dict[str, str] = {
    "loa_exceeds_position": "loa",
    "loa_overhang": "loa",
    "loa_shared_pier": "loa",
    "loa_recalc_exceeds": "loa",
    "loa_recalc_sum_red": "loa",
    "loa_recalc_sum_yellow": "loa",
    "loa_recalc_sum_green": "loa",
    "combined_loa_red": "loa",
    "combined_loa_orange": "loa",
    "eta_close": "schedule",
    "eta_before_min": "schedule",
    "filo_eta_violation": "schedule",
    "filo_etd_violation": "schedule",
    "position_occupied": "position",
    "lta_slot_reserved": "position",
    "lta_priority_conflict": "position",
    "no_position_available": "position",
    "combined_position_retired": "position",
    "beam_exceeds_position": "card",
    "draft_too_deep": "card",
    "multi_port_conflict": "card",
    "multi_port_proximity": "card",
    "lta_beyond_horizon": "card",
    "lta_horizon_denied": "card",
}

CONFLICT_CHIP_LABEL_BY_CODE: dict[str, str] = {
    "multi_port_proximity": "Proximidad",
    "multi_port_conflict": "Multi-puerto",
    "loa_exceeds_position": "Eslora",
    "loa_overhang": "Eslora",
    "loa_shared_pier": "Eslora",
    "loa_recalc_exceeds": "Eslora",
    "loa_recalc_sum_red": "Eslora",
    "loa_recalc_sum_yellow": "Eslora",
    "loa_recalc_sum_green": "Eslora",
    "combined_loa_red": "Eslora",
    "combined_loa_orange": "Eslora",
    "eta_close": "Horario",
    "eta_before_min": "Horario",
    "filo_eta_violation": "FILO",
    "filo_etd_violation": "FILO",
    "position_occupied": "Posición",
    "no_position_available": "Posición",
    "combined_position_retired": "Posición",
    "lta_slot_reserved": "LTA",
    "lta_priority_conflict": "LTA",
    "lta_beyond_horizon": "LTA",
    "lta_horizon_denied": "LTA",
    "beam_exceeds_position": "Manga",
    "draft_too_deep": "Calado",
}

CHIP_LABEL_BY_TYPE: dict[str, str] = {
    "proximity": "Proximidad",
    "loa": "Eslora",
    "schedule": "Horario",
    "position": "Posición",
    "lta": "LTA",
    "physical": "Físico",
}

CODE_TO_TYPE: dict[str, str] = {}
for _type, codes in {
    "proximity": ["multi_port_proximity", "multi_port_conflict"],
    "loa": [
        "loa_exceeds_position",
        "loa_overhang",
        "loa_shared_pier",
        "loa_recalc_exceeds",
        "loa_recalc_sum_red",
        "loa_recalc_sum_yellow",
        "loa_recalc_sum_green",
        "combined_loa_red",
        "combined_loa_orange",
    ],
    "schedule": [
        "eta_close",
        "eta_before_min",
        "filo_eta_violation",
        "filo_etd_violation",
    ],
    "position": [
        "position_occupied",
        "no_position_available",
        "combined_position_retired",
        "lta_slot_reserved",
    ],
    "lta": [
        "lta_priority_conflict",
        "lta_beyond_horizon",
        "lta_horizon_denied",
    ],
    "physical": ["beam_exceeds_position", "draft_too_deep"],
}.items():
    for code in codes:
        CODE_TO_TYPE[code] = _type

_SEV_RANK = {"red": 3, "yellow": 2, "green": 1}


def _max_severity(
    current: str | None,
    candidate: str,
) -> str:
    if not current:
        return candidate
    if _SEV_RANK.get(candidate, 0) > _SEV_RANK.get(current, 0):
        return candidate
    return current


def frame_severity(
    *,
    has_conflict: bool,
    conflict_severity: str | None,
    snapshot: list | None,
) -> str | None:
    if not has_conflict:
        return None
    direct = conflict_severity
    if direct in {"red", "yellow", "green"}:
        return direct
    return max_snapshot_severity(snapshot) or "yellow"


def conflict_chips_from_snapshot(snapshot: list | None) -> list[dict]:
    by_key: dict[str, dict] = {}
    for item in snapshot or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        if not code:
            continue
        conflict_type = CODE_TO_TYPE.get(code, "other")
        label = (
            CHIP_LABEL_BY_TYPE[conflict_type]
            if conflict_type in CHIP_LABEL_BY_TYPE
            else CONFLICT_CHIP_LABEL_BY_CODE.get(code, "Aviso")
        )
        severity = resolve_issue_severity(item)
        key = conflict_type if conflict_type != "other" else f"other:{label}"
        existing = by_key.get(key)
        if existing:
            existing["severity"] = _max_severity(existing["severity"], severity)
        else:
            by_key[key] = {
                "type": conflict_type,
                "label": label,
                "severity": severity,
            }
    order = {"red": 0, "yellow": 1, "green": 2}
    return sorted(
        by_key.values(),
        key=lambda chip: order.get(str(chip.get("severity")), 99),
    )


def conflict_highlights_from_snapshot(
    *,
    has_conflict: bool,
    conflict_severity: str | None,
    snapshot: list | None,
) -> dict:
    severity = frame_severity(
        has_conflict=has_conflict,
        conflict_severity=conflict_severity,
        snapshot=snapshot,
    )
    if not severity:
        return {
            "severity": None,
            "frame_card": False,
            "highlight_loa": False,
            "highlight_schedule": False,
            "highlight_position": False,
            "loa_severity": None,
            "schedule_severity": None,
            "position_severity": None,
        }

    frame_card = False
    loa_severity: str | None = None
    schedule_severity: str | None = None
    position_severity: str | None = None
    items = snapshot or []

    if not items:
        frame_card = True
    else:
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            sev = CONFLICT_SEVERITY_BY_CODE.get(code) or resolve_issue_severity(item)
            target = CONFLICT_HIGHLIGHT_BY_CODE.get(code, "card")
            if target == "loa":
                loa_severity = _max_severity(loa_severity, sev)
            elif target == "schedule":
                schedule_severity = _max_severity(schedule_severity, sev)
            elif target == "position":
                position_severity = _max_severity(position_severity, sev)
            else:
                frame_card = True

    return {
        "severity": severity,
        "frame_card": frame_card,
        "highlight_loa": loa_severity is not None,
        "highlight_schedule": schedule_severity is not None,
        "highlight_position": position_severity is not None,
        "loa_severity": loa_severity,
        "schedule_severity": schedule_severity,
        "position_severity": position_severity,
    }


def booking_conflict_filter_ctx(booking) -> dict:
    """Normalized conflict fields for list/availability/proximity filters."""
    return {
        "has_conflict": bool(getattr(booking, "has_conflict", False)),
        "conflict_severity": getattr(booking, "conflict_severity", None),
        "conflict_snapshot": getattr(booking, "conflict_snapshot", None) or [],
    }


def booking_conflict_display(
    *,
    has_conflict: bool,
    conflict_severity: str | None,
    snapshot: list | None,
) -> dict:
    """API-ready conflict chips + card highlight hints."""
    snapshot = snapshot or []
    resolved_severity = frame_severity(
        has_conflict=bool(has_conflict),
        conflict_severity=conflict_severity,
        snapshot=snapshot,
    )
    return {
        "conflict_chips": conflict_chips_from_snapshot(snapshot),
        "conflict_highlights": conflict_highlights_from_snapshot(
            has_conflict=bool(has_conflict),
            conflict_severity=resolved_severity,
            snapshot=snapshot,
        ),
    }


def cell_matches_conflict_filter(
    cell: dict,
    *,
    has_conflict: bool | None = None,
    conflict_severity: str | None = None,
    conflict_type: str | None = None,
) -> bool:
    snapshot = cell.get("conflict_snapshot") or []
    cell_has_conflict = bool(cell.get("has_conflict"))
    effective_severity = frame_severity(
        has_conflict=cell_has_conflict,
        conflict_severity=cell.get("conflict_severity"),
        snapshot=snapshot,
    )

    if has_conflict is True and not cell_has_conflict:
        return False
    if has_conflict is False and cell_has_conflict:
        return False
    if conflict_severity in {"yellow", "red", "green"}:
        if effective_severity != conflict_severity:
            return False
    if conflict_type:
        if conflict_type not in CONFLICT_TYPES:
            return False
        if not snapshot_has_conflict_type(snapshot, conflict_type):
            return False
    return True
