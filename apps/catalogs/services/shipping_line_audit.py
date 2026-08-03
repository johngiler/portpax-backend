from __future__ import annotations

from typing import Any


def snapshot_shipping_line(line) -> dict[str, Any]:
    group = getattr(line, "group", None)
    return {
        "id": line.pk,
        "code": line.code or "",
        "name": line.name or "",
        "group_id": line.group_id,
        "group_name": getattr(group, "name", "") or "",
        "is_active": bool(line.is_active),
        "has_logo": bool(line.logo),
    }


def _field_change(before: Any, after: Any) -> dict[str, Any] | None:
    if before == after:
        return None
    return {"from": before, "to": after}


def diff_shipping_line_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "code",
        "name",
        "group_id",
        "group_name",
        "is_active",
        "has_logo",
    ):
        delta = _field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    return changes
