"""Operational conflict severity (non-blocking)."""

from __future__ import annotations

CONFLICT_SEVERITY_BY_CODE: dict[str, str] = {
    # Occupation / schedule
    "position_occupied": "red",
    "lta_priority_conflict": "red",
    "eta_close": "yellow",
    "eta_before_min": "yellow",
    # Dimensions
    "loa_exceeds_position": "red",
    "loa_overhang": "yellow",
    "loa_shared_pier": "yellow",
    "beam_exceeds_position": "red",
    "draft_too_deep": "red",
    "mooring_capacity": "yellow",
    "combined_position_retired": "red",
    # Shared pier / recalc
    "loa_recalc_exceeds": "red",
    "loa_recalc_sum_red": "red",
    "loa_recalc_sum_yellow": "yellow",
    "loa_recalc_sum_green": "green",
    # Pair constraint (legacy)
    "combined_loa_red": "red",
    "combined_loa_orange": "yellow",
    # FILO
    "filo_eta_violation": "red",
    "filo_etd_violation": "red",
    # LTA
    "lta_slot_reserved": "red",
    "lta_beyond_horizon": "yellow",
    "lta_horizon_denied": "yellow",
    # Multi-port same vessel (same day or ±2 days)
    "multi_port_conflict": "yellow",
    "multi_port_proximity": "yellow",
    # Assignment
    "no_position_available": "yellow",
}

INFO_ONLY_CODES = frozenset({"loa_recalc_sum_green"})


def severity_for_code(code: str, *, level: str | None = None) -> str:
    if code in CONFLICT_SEVERITY_BY_CODE:
        return CONFLICT_SEVERITY_BY_CODE[code]
    if level == "error":
        return "red"
    if level == "info":
        return "green"
    return "yellow"
