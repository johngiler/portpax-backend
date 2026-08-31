from __future__ import annotations

from typing import Any


def position_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "position",
        "code": snap.get("short_code") or snap.get("code") or "",
        "position_code": snap.get("short_code") or snap.get("code") or "",
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
        "name": snap.get("short_code") or snap.get("code") or "",
    }


def berth_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    label = snap.get("name") or snap.get("code") or ""
    return {
        "kind": "berth",
        "code": snap.get("code") or "",
        "name": label,
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def bollard_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "bollard",
        "code": snap.get("label") or f"{snap.get('capacity_t')} t",
        "name": snap.get("label") or f"{snap.get('quantity')}× {snap.get('capacity_t')} t",
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def fender_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "fender",
        "code": snap.get("fender_type") or "",
        "name": f"{snap.get('quantity')}× {snap.get('fender_type')}",
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def port_image_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    label = snap.get("caption") or f"imagen #{snap.get('id')}"
    return {
        "kind": "port_image",
        "code": label,
        "name": label,
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def berth_image_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    label = snap.get("caption") or f"imagen #{snap.get('id')}"
    return {
        "kind": "berth_image",
        "code": label,
        "name": label,
        "berth_code": snap.get("berth_code") or "",
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def position_image_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    label = snap.get("caption") or f"imagen #{snap.get('id')}"
    return {
        "kind": "position_image",
        "code": label,
        "name": label,
        "position_code": snap.get("position_short_code") or "",
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def nesting_rule_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    pair = f"{snap.get('outer_position_code')} → {snap.get('inner_position_code')}"
    return {
        "kind": "nesting_rule",
        "code": pair,
        "name": pair,
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }


def loa_recalc_rule_audit_entity(snap: dict[str, Any]) -> dict[str, Any]:
    pair = f"{snap.get('position_a_code')}↔{snap.get('position_b_code')}"
    return {
        "kind": "loa_recalc_rule",
        "code": pair,
        "name": pair,
        "port_code": snap.get("port_code") or "",
        "port_name": snap.get("port_name") or "",
    }
