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
        "is_active",
        "has_logo",
    ):
        delta = _field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta

    if before.get("group_id") != after.get("group_id"):
        changes["group_id"] = {
            "from": before.get("group_id"),
            "to": after.get("group_id"),
            "from_name": before.get("group_name") or "",
            "to_name": after.get("group_name") or "",
        }
    elif before.get("group_name") != after.get("group_name"):
        delta = _field_change(before.get("group_name"), after.get("group_name"))
        if delta is not None:
            changes["group_name"] = delta
    return changes
