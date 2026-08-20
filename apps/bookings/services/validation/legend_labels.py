"""Friendly labels for operator-facing validation / conflict legends."""

from __future__ import annotations

from apps.catalogs.utils.position_code import position_short_code


def port_legend_label(port) -> str:
    """Port name; include commercial name when set (same as UI catalogs)."""
    if port is None:
        return ""
    name = (getattr(port, "name", None) or "").strip() or str(
        getattr(port, "code", "") or ""
    )
    commercial = (getattr(port, "commercial_name", None) or "").strip()
    if commercial:
        return f"{name} ({commercial})"
    return name


def position_legend_label(position, *, port=None) -> str:
    """Short berth code ops know (E1, P2) — never raw `puerto_plata-E1`."""
    if position is None:
        return "?"
    port_obj = port or getattr(position, "port", None)
    port_code = getattr(port_obj, "code", None) or ""
    code = getattr(position, "code", None) or "?"
    if port_code:
        return position_short_code(str(port_code), str(code))
    return str(code)


def vessel_legend_label(vessel, *, fallback: str = "Este barco") -> str:
    if vessel is None:
        return fallback
    name = (getattr(vessel, "name", None) or "").strip()
    return name or fallback
