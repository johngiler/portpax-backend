from __future__ import annotations

from typing import Any

from apps.catalogs.services.port_catalog_audit.common import diff_snapshots


POSITION_DIFF_KEYS = (
    "code",
    "position_type",
    "berth_id",
    "max_loa_m",
    "min_loa_m",
    "max_beam_m",
    "min_draft_m",
    "min_eta",
    "bollard_count",
    "fender_count",
    "bollard_allocations",
    "fender_allocations",
    "effective_from",
    "effective_until",
    "notes",
    "latitude",
    "longitude",
    "sort_order",
    "is_active",
)

BERTH_DIFF_KEYS = (
    "code",
    "name",
    "length_m",
    "width_m",
    "walkway_length_m",
    "walkway_width_m",
    "min_draft_m",
    "notes",
    "latitude",
    "longitude",
    "sort_order",
    "is_active",
)

BOLLARD_DIFF_KEYS = (
    "capacity_t",
    "bollard_type",
    "quantity",
    "label",
    "sort_order",
    "notes",
    "is_active",
)

FENDER_DIFF_KEYS = (
    "fender_type",
    "quantity",
    "sort_order",
    "notes",
    "is_active",
)

IMAGE_DIFF_KEYS = ("caption", "sort_order", "is_cover", "has_image")

NESTING_DIFF_KEYS = (
    "outer_position_id",
    "inner_position_id",
    "enforce_eta",
    "enforce_etd",
    "is_active",
    "notes",
)

LOA_RECALC_DIFF_KEYS = (
    "position_a_id",
    "position_b_id",
    "max_loa_m",
    "separation_m",
    "yellow_from_m",
    "red_from_m",
    "is_active",
    "notes",
)


def diff_position_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes = diff_snapshots(before, after, POSITION_DIFF_KEYS)
    if before.get("berth_id") != after.get("berth_id"):
        changes["berth_id"] = {
            "from": before.get("berth_id"),
            "to": after.get("berth_id"),
            "from_code": before.get("berth_code") or "",
            "to_code": after.get("berth_code") or "",
        }
    return changes


def diff_berth_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, BERTH_DIFF_KEYS)


def diff_bollard_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, BOLLARD_DIFF_KEYS)


def diff_fender_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, FENDER_DIFF_KEYS)


def diff_port_image_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, IMAGE_DIFF_KEYS)


def diff_berth_image_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, IMAGE_DIFF_KEYS)


def diff_position_image_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return diff_snapshots(before, after, IMAGE_DIFF_KEYS)


def diff_nesting_rule_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes = diff_snapshots(before, after, NESTING_DIFF_KEYS)
    for key, code_key in (
        ("outer_position_id", "outer_position_code"),
        ("inner_position_id", "inner_position_code"),
    ):
        if before.get(key) != after.get(key) and key in changes:
            changes[key] = {
                **changes[key],
                "from_code": before.get(code_key) or "",
                "to_code": after.get(code_key) or "",
            }
    return changes


def diff_loa_recalc_rule_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes = diff_snapshots(before, after, LOA_RECALC_DIFF_KEYS)
    for key, code_key in (
        ("position_a_id", "position_a_code"),
        ("position_b_id", "position_b_code"),
    ):
        if before.get(key) != after.get(key) and key in changes:
            changes[key] = {
                **changes[key],
                "from_code": before.get(code_key) or "",
                "to_code": after.get(code_key) or "",
            }
    return changes
