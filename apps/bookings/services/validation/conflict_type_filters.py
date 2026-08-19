"""Conflict type groups for list/availability filters."""

from __future__ import annotations

from django.db.models import Q

CONFLICT_TYPE_CODES: dict[str, list[str]] = {
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
}

CONFLICT_TYPES = frozenset(CONFLICT_TYPE_CODES.keys())


def codes_for_conflict_type(conflict_type: str) -> list[str]:
    return list(CONFLICT_TYPE_CODES.get(conflict_type, []))


def snapshot_has_conflict_type(snapshot: list | None, conflict_type: str) -> bool:
    codes = set(codes_for_conflict_type(conflict_type))
    if not codes:
        return False
    for item in snapshot or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("code") or "") in codes:
            return True
    return False


def filter_queryset_by_conflict_type(qs, conflict_type: str):
    codes = codes_for_conflict_type(conflict_type)
    if not codes:
        return qs
    q = Q()
    for code in codes:
        q |= Q(conflict_snapshot__contains=[{"code": code}])
    return qs.filter(has_conflict=True).filter(q)
