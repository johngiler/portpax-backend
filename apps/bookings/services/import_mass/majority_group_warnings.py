"""Soft warnings when a preview batch has a clear majority shipping-line group."""

from __future__ import annotations

from collections import Counter
from typing import Any

GROUP_MAJORITY_MARK = "Grupo mayoritario:"


def _strip_majority_warnings(warnings: list[str] | None) -> list[str]:
    return [
        w
        for w in (warnings or [])
        if not str(w).startswith(GROUP_MAJORITY_MARK)
    ]


def annotate_majority_group_warnings(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    If most resolved rows share one shipping-line group, flag the minority.

    Soft only: appends to ``warnings`` (does not change ``issues`` / ``selectable``).
    No clear majority or ties → no flags.
    """
    group_ids = [
        int(row["shipping_line_group_id"])
        for row in rows
        if row.get("shipping_line_group_id") is not None
    ]
    if len(group_ids) < 2:
        for row in rows:
            row["warnings"] = _strip_majority_warnings(row.get("warnings"))
        return rows

    counts = Counter(group_ids)
    ranked = counts.most_common(2)
    majority_id, majority_count = ranked[0]
    if majority_count <= len(group_ids) / 2:
        for row in rows:
            row["warnings"] = _strip_majority_warnings(row.get("warnings"))
        return rows
    if len(ranked) >= 2 and ranked[1][1] == majority_count:
        for row in rows:
            row["warnings"] = _strip_majority_warnings(row.get("warnings"))
        return rows

    majority_name = "el grupo mayoritario"
    for row in rows:
        if row.get("shipping_line_group_id") == majority_id:
            majority_name = (
                row.get("shipping_line_group_name") or majority_name
            )
            break

    for row in rows:
        warnings = _strip_majority_warnings(row.get("warnings"))
        gid = row.get("shipping_line_group_id")
        if gid is not None and int(gid) != majority_id:
            other = row.get("shipping_line_group_name") or "otro grupo"
            warnings.append(
                f"{GROUP_MAJORITY_MARK} parece que el barco en esta reserva "
                f"pertenece a otra naviera (mayoría: {majority_name}; "
                f"esta fila: {other})."
            )
        row["warnings"] = warnings
    return rows
