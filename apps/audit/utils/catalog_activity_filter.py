"""Map catalog audit operation filters to action names."""

from __future__ import annotations


def catalog_actions_for_operation(
    operation: str,
    catalog_actions: tuple[str, ...],
) -> tuple[str, ...]:
    if operation == "create":
        return tuple(
            action
            for action in catalog_actions
            if action == "created" or action.endswith("_created")
        )
    if operation == "update":
        return tuple(
            action
            for action in catalog_actions
            if action == "updated" or action.endswith("_updated")
        )
    if operation == "delete":
        return tuple(
            action
            for action in catalog_actions
            if action == "deleted" or action.endswith("_deleted")
        )
    return catalog_actions


def norm_activity_operation(
    value: str | None,
    allowed: tuple[str, ...],
    default: str = "all",
) -> str:
    lowered = (value or default).lower()
    return lowered if lowered in allowed else default
