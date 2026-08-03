"""Request context for audit rows (where / how the action happened)."""

from __future__ import annotations

from typing import Any


def client_ip(request) -> str:
    if request is None:
        return ""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    return (request.META.get("REMOTE_ADDR") or "")[:64]


def extract_request_context(request) -> dict[str, str]:
    """Where the actor acted: IP, user-agent, path (audit + ops diagnostics)."""
    if request is None:
        return {}
    ua = request.META.get("HTTP_USER_AGENT") or ""
    path = getattr(request, "path", "") or ""
    ctx: dict[str, str] = {}
    ip = client_ip(request)
    if ip:
        ctx["ip"] = ip
    if ua:
        ctx["user_agent"] = ua[:500]
    if path:
        ctx["path"] = path[:255]
    return ctx


def with_audit_context(
    changes: dict[str, Any] | None,
    request=None,
    *,
    entity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge field-level changes with audit context.
    - Field diffs stay at top level (from/to) for ops.
    - `context` = IP / UA / path for audit.
    - `entity` = stable subject snapshot (codes, dates) for ops after FK null.
    """
    payload: dict[str, Any] = dict(changes or {})
    ctx = extract_request_context(request)
    if ctx:
        payload["context"] = ctx
    if entity:
        payload["entity"] = entity
    return payload
