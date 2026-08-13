"""Operational conflict severity (non-blocking).

Paint rules:
- yellow — default non-blocking aviso (ops can still save)
- red — very heavy berthing / physical / FILO / semaphore red
- green — traffic-light OK (LOA recalc sum under yellow)
"""

from __future__ import annotations

CONFLICT_SEVERITY_BY_CODE: dict[str, str] = {
    # Heavy (even though non-blocking for create/save)
    "position_occupied": "red",
    "lta_priority_conflict": "red",
    "loa_exceeds_position": "red",
    "beam_exceeds_position": "red",
    "draft_too_deep": "red",
    "combined_position_retired": "red",
    "loa_recalc_exceeds": "red",
    "loa_recalc_sum_red": "red",
    "combined_loa_red": "red",
    "filo_eta_violation": "red",
    "filo_etd_violation": "red",
    # Non-blocking avisos (amber)
    "eta_close": "yellow",
    "eta_before_min": "yellow",
    "loa_overhang": "yellow",
    "loa_shared_pier": "yellow",
    "mooring_capacity": "yellow",
    "loa_recalc_sum_yellow": "yellow",
    "combined_loa_orange": "yellow",
    "lta_slot_reserved": "yellow",
    "lta_beyond_horizon": "yellow",
    "lta_horizon_denied": "yellow",
    "multi_port_conflict": "yellow",
    "multi_port_proximity": "yellow",
    "no_position_available": "yellow",
    # Traffic light OK
    "loa_recalc_sum_green": "green",
}

INFO_ONLY_CODES = frozenset({"loa_recalc_sum_green"})


def severity_for_code(code: str, *, level: str | None = None) -> str:
    if code in CONFLICT_SEVERITY_BY_CODE:
        return CONFLICT_SEVERITY_BY_CODE[code]
    if level == "info":
        return "green"
    # Default non-blocking aviso → amber (not red).
    return "yellow"


def resolve_issue_severity(issue: dict) -> str:
    """Prefer code map so paint stays consistent even with stale snapshots."""
    code = str(issue.get("code") or "")
    if code in CONFLICT_SEVERITY_BY_CODE:
        return CONFLICT_SEVERITY_BY_CODE[code]
    sev = issue.get("severity")
    if sev in {"red", "yellow", "green"}:
        return str(sev)
    return severity_for_code(code, level=issue.get("level"))
