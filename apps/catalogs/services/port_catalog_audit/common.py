from __future__ import annotations

from typing import Any


def dec(value) -> float | None:
    if value is None:
        return None
    return float(value)


def field_change(before: Any, after: Any) -> dict[str, Any] | None:
    if before == after:
        return None
    return {"from": before, "to": after}


def diff_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    keys: tuple[str, ...],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in keys:
        delta = field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    return changes


def port_context(port) -> dict[str, Any]:
    return {
        "port_id": port.pk,
        "port_code": port.code or "",
        "port_name": port.name or "",
    }
