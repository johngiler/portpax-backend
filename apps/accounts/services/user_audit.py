"""Helpers to snapshot managed users and build audit change payloads."""

from __future__ import annotations

from typing import Any

from apps.accounts.models import UserProfile, UserRole

ROLE_LABELS: dict[str, str] = {
    UserRole.ADMIN: "Administrador",
    UserRole.BOOKING_OPERATOR: "Operador de booking",
    UserRole.PORT_OPERATOR: "Operador de puerto",
    UserRole.VIEWER: "Solo lectura",
}


def role_label(role: str | None) -> str:
    if not role:
        return "—"
    return ROLE_LABELS.get(role, role)


def user_display_name(user) -> str:
    if user is None:
        return ""
    full = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    if full:
        return full
    return user.get_username()


def snapshot_user(user) -> dict[str, Any]:
    try:
        role = user.profile.role
    except UserProfile.DoesNotExist:
        role = ""
    port_ids = sorted(user.port_access.values_list("port_id", flat=True))
    return {
        "id": user.pk,
        "username": user.get_username(),
        "display": user_display_name(user),
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "is_active": bool(user.is_active),
        "role": role or "",
        "port_ids": port_ids,
    }


def _field_change(before: Any, after: Any) -> dict[str, Any] | None:
    if before == after:
        return None
    return {"from": before, "to": after}


def diff_user_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    password_changed: bool = False,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "role",
        "port_ids",
    ):
        delta = _field_change(before.get(key), after.get(key))
        if delta is not None:
            changes[key] = delta
    if password_changed:
        changes["password"] = {"changed": True}
    return changes


def summarize_user_changes(changes: dict[str, Any]) -> str:
    if not changes:
        return "Actualización de usuario"
    parts: list[str] = []
    if "role" in changes:
        parts.append(
            f"rol {role_label(changes['role'].get('from'))} → "
            f"{role_label(changes['role'].get('to'))}"
        )
    if "is_active" in changes:
        before = "Activo" if changes["is_active"].get("from") else "Inactivo"
        after = "Activo" if changes["is_active"].get("to") else "Inactivo"
        parts.append(f"estado {before} → {after}")
    if "email" in changes:
        parts.append("correo")
    if "username" in changes:
        parts.append("usuario")
    if "first_name" in changes or "last_name" in changes:
        parts.append("nombre")
    if "port_ids" in changes:
        parts.append("puertos")
    if "password" in changes:
        parts.append("contraseña")
    if not parts:
        return "Actualización de usuario"
    return "Cambios: " + ", ".join(parts)
