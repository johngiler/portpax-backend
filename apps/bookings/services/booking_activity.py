"""Unified booking activity feed (single audits + mass import batches)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import BookingAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.bookings.models import Booking, BookingImportBatch

SINGLE_ACTIONS = (
    "created",
    "operational_update",
    "identity_update",
    "status_change",
    "lta_linked",
    "lta_unlinked",
    "deleted",
)

CREATE_AUDIT_ACTIONS = ("created",)
UPDATE_AUDIT_ACTIONS = (
    "operational_update",
    "identity_update",
    "status_change",
    "lta_linked",
    "lta_unlinked",
)
DELETE_AUDIT_ACTIONS = ("deleted",)
LTA_LINK_ACTIONS = ("lta_linked", "lta_unlinked")
BOOKING_UPDATE_ACTIONS = tuple(
    action for action in UPDATE_AUDIT_ACTIONS if action not in LTA_LINK_ACTIONS
)
LTA_AGREEMENT_SOURCES = ("lta_agreement",)

# Legacy single-axis filter (Tipo dropdown — deprecated, kept for compat).
ACTIVITY_KINDS = (
    "all",
    "single",
    "bulk",
    "wizard",
    "mass_import",
    "berthing_import",
    "lta_generate",
)

ACTIVITY_OPERATIONS = ("all", "create", "update", "delete")
ACTIVITY_ORIGINS = (
    "all",
    "wizard",
    "mass_import",
    "berthing_import",
    "lta_generate",
    "booking_update",
    "mass_update",
    "lta_agreement",
    "lta_link",  # legacy alias of lta_agreement
)

MASS_IMPORT_SOURCES = ("mass_import", "import_file", "import_paste")


def _norm(value: str | None, allowed: tuple[str, ...], default: str) -> str:
    lowered = (value or default).lower()
    return lowered if lowered in allowed else default


def _legacy_kind_filters(kind: str) -> dict[str, Any]:
    """Map deprecated kind param to operation/origin/include flags."""
    if kind == "single":
        return {"include_bulk": False}
    if kind == "bulk":
        return {"operation": "create", "include_single": False}
    if kind == "wizard":
        return {"operation": "create", "origin": "wizard"}
    if kind == "mass_import":
        return {"operation": "create", "origin": "mass_import"}
    if kind == "berthing_import":
        return {"operation": "create", "origin": "berthing_import"}
    if kind == "lta_generate":
        return {"operation": "create", "origin": "lta_generate"}
    return {}


def _resolve_activity_filters(
    *,
    operation: str = "all",
    origin: str = "all",
    kind: str | None = None,
) -> dict[str, Any]:
    operation = _norm(operation, ACTIVITY_OPERATIONS, "all")
    origin = _norm(origin, ACTIVITY_ORIGINS, "all")
    if origin == "lta_link":
        origin = "lta_agreement"

    include_single = True
    include_bulk = True
    audit_actions: tuple[str, ...] | None = None
    source_filter: str | None = None
    exclude_sources: tuple[str, ...] = ()
    lta_agreement_only = False
    batch_kind: str | None = None

    legacy = _legacy_kind_filters(kind) if kind and kind not in ("all", "") else {}
    if legacy.get("include_single") is False:
        include_single = False
    if legacy.get("include_bulk") is False:
        include_bulk = False
    if legacy.get("operation"):
        operation = legacy["operation"]
    if legacy.get("origin"):
        origin = legacy["origin"]

    if operation == "create":
        audit_actions = CREATE_AUDIT_ACTIONS
    elif operation == "update":
        audit_actions = UPDATE_AUDIT_ACTIONS
        include_bulk = False
    elif operation == "delete":
        audit_actions = DELETE_AUDIT_ACTIONS
        include_bulk = False
    else:
        audit_actions = SINGLE_ACTIONS

    if origin == "wizard":
        include_bulk = False
        if operation in ("all", "create"):
            source_filter = "wizard"
            audit_actions = _intersect_actions(audit_actions, CREATE_AUDIT_ACTIONS)
        elif operation == "update":
            audit_actions = _intersect_actions(audit_actions, BOOKING_UPDATE_ACTIONS)
            exclude_sources = ("bulk_edit", *LTA_AGREEMENT_SOURCES)
    elif origin == "lta_generate":
        source_filter = "lta_generate"
        include_bulk = False
        audit_actions = _intersect_actions(audit_actions, CREATE_AUDIT_ACTIONS)
    elif origin == "mass_import":
        batch_kind = "mass_import"
        include_single = False
        if operation in ("all", "create"):
            audit_actions = CREATE_AUDIT_ACTIONS
        else:
            include_bulk = False
            audit_actions = ()
    elif origin == "berthing_import":
        # One-time CLI import: aggregate batch row only (no per-booking audits in feed).
        batch_kind = "berthing_import"
        include_single = False
        if operation in ("all", "create"):
            audit_actions = CREATE_AUDIT_ACTIONS
        else:
            include_bulk = False
            audit_actions = ()
    elif origin == "lta_agreement":
        include_bulk = False
        lta_agreement_only = True
        if operation in ("all", "update"):
            audit_actions = _intersect_actions(audit_actions, UPDATE_AUDIT_ACTIONS)
        elif operation == "create":
            include_single = False
            audit_actions = ()
    elif origin == "mass_update":
        include_bulk = False
        source_filter = "bulk_edit"
        audit_actions = _intersect_actions(audit_actions, BOOKING_UPDATE_ACTIONS)
    elif origin == "booking_update":
        include_bulk = False
        audit_actions = _intersect_actions(audit_actions, BOOKING_UPDATE_ACTIONS)
        exclude_sources = ("bulk_edit", *LTA_AGREEMENT_SOURCES)

    if operation == "create" and origin in ("lta_agreement", "booking_update"):
        include_single = False
        include_bulk = False
        audit_actions = ()
    if operation == "update" and origin in (
        "lta_generate",
        "mass_import",
        "berthing_import",
    ):
        include_single = False
        include_bulk = False
        audit_actions = ()
    if operation == "delete" and origin not in ("all",):
        include_single = False
        audit_actions = ()

    return {
        "include_single": include_single,
        "include_bulk": include_bulk,
        "audit_actions": audit_actions,
        "source_filter": source_filter,
        "exclude_sources": exclude_sources,
        "lta_agreement_only": lta_agreement_only,
        "batch_kind": batch_kind,
    }


def _intersect_actions(
    current: tuple[str, ...] | None,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    if not current:
        return allowed
    return tuple(action for action in current if action in allowed)


def _user_display(user) -> str | None:
    if user is None:
        return None
    return user.get_username()


def _parse_bound(value: str | None, *, end_of_day: bool = False):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    d = parse_date(value)
    if d is None:
        return None
    if end_of_day:
        dt = datetime.combine(d, datetime.max.time().replace(microsecond=0))
    else:
        dt = datetime.combine(d, datetime.min.time())
    return timezone.make_aware(dt)


def _single_item(entry: BookingAuditEntry) -> dict[str, Any]:
    code = entry.booking_code or None
    if not code and entry.booking_id and entry.booking is not None:
        code = entry.booking.booking_code
    changes = entry.changes or {}
    entity = changes.get("entity") if isinstance(changes, dict) else None
    return {
        "kind": "single",
        "audit_id": entry.id,
        "action": entry.action,
        "occurred_at": entry.created_at,
        "user_display": _user_display(entry.user),
        "summary": entry.summary,
        "booking_id": entry.booking_id,
        "booking_code": code,
        "batch_id": None,
        "created_count": None,
        "failed_count": None,
        "not_created_count": None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def _bulk_item(batch: BookingImportBatch) -> dict[str, Any]:
    return {
        "kind": "bulk",
        "action": "bulk_create",
        "occurred_at": batch.created_at,
        "user_display": _user_display(batch.created_by),
        "summary": (
            f"Importación: {batch.created_count} creadas, "
            f"{batch.failed_count} fallidas, "
            f"{max(0, len(batch.retry_rows or []) - batch.failed_count)} no creadas"
        ),
        "booking_id": None,
        "booking_code": None,
        "batch_id": batch.id,
        "created_count": batch.created_count,
        "failed_count": batch.failed_count,
        "not_created_count": max(
            0, len(batch.retry_rows or []) - batch.failed_count
        ),
        "label": batch.label,
    }


def _audit_queryset(
    *,
    allowed_ports: list[int] | None,
    date_from,
    date_to,
    actor_system: bool = False,
    actor_user_id: int | None = None,
    actions: tuple[str, ...] | None = None,
    source: str | None = None,
    exclude_sources: tuple[str, ...] = (),
    lta_agreement_only: bool = False,
    booking_id: int | None = None,
):
    actions = actions if actions is not None else SINGLE_ACTIONS
    if not actions:
        return BookingAuditEntry.objects.none()

    qs = (
        BookingAuditEntry.objects.filter(action__in=actions)
        .select_related("booking", "user")
        .exclude(changes__has_key="import_batch_id")
    )
    if booking_id is not None:
        qs = qs.filter(booking_id=booking_id)
    if source:
        if source == "mass_import":
            qs = qs.filter(changes__source__in=MASS_IMPORT_SOURCES)
        else:
            qs = qs.filter(changes__source=source)
    if exclude_sources:
        for excluded in exclude_sources:
            qs = qs.filter(
                ~Q(changes__has_key="source") | ~Q(changes__source=excluded)
            )
    if lta_agreement_only:
        qs = qs.filter(
            Q(action__in=LTA_LINK_ACTIONS)
            | Q(changes__source__in=LTA_AGREEMENT_SOURCES)
        )
    if allowed_ports is not None:
        qs = qs.filter(
            Q(port_id__in=allowed_ports) | Q(booking__port_id__in=allowed_ports)
        )
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    if actor_system:
        qs = qs.filter(user__isnull=True)
    elif actor_user_id is not None:
        qs = qs.filter(user_id=actor_user_id)
    return qs.order_by("-created_at")


def _batch_queryset(
    *,
    allowed_ports: list[int] | None,
    user,
    date_from,
    date_to,
    actor_system: bool = False,
    actor_user_id: int | None = None,
    kind: str | None = None,
):
    qs = BookingImportBatch.objects.select_related("created_by")
    if kind == "berthing_import":
        qs = qs.filter(label__startswith="BERTHING PAPERS")
    elif kind == "mass_import":
        qs = qs.exclude(label__startswith="BERTHING PAPERS")
    if allowed_ports is not None:
        qs = qs.filter(created_by=user)
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    if actor_system:
        qs = qs.filter(created_by__isnull=True)
    elif actor_user_id is not None:
        qs = qs.filter(created_by_id=actor_user_id)
    return qs.order_by("-created_at")


def list_booking_activity_actors(
    *,
    user,
    allowed_ports: list[int] | None,
) -> dict[str, Any]:
    """Users that appear as actors in booking history the caller can see."""
    audit_qs = BookingAuditEntry.objects.filter(action__in=SINGLE_ACTIONS).exclude(
        changes__has_key="import_batch_id"
    )
    if allowed_ports is not None:
        audit_qs = audit_qs.filter(
            Q(port_id__in=allowed_ports) | Q(booking__port_id__in=allowed_ports)
        )
    audit_ids = set(
        audit_qs.exclude(user_id=None).values_list("user_id", flat=True).distinct()
    )
    has_system_audit = audit_qs.filter(user_id__isnull=True).exists()

    batch_qs = BookingImportBatch.objects.all()
    if allowed_ports is not None:
        batch_qs = batch_qs.filter(created_by=user)
    batch_ids = set(
        batch_qs.exclude(created_by_id=None)
        .values_list("created_by_id", flat=True)
        .distinct()
    )
    has_system_batch = batch_qs.filter(created_by_id__isnull=True).exists()

    return {
        "results": actor_options_from_ids(audit_ids | batch_ids),
        "has_system": has_system_audit or has_system_batch,
    }


def build_booking_activity(
    *,
    user,
    allowed_ports: list[int] | None,
    kind: str = "all",
    operation: str = "all",
    origin: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    booking_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = _norm(kind, ACTIVITY_KINDS, "all")
    filters = _resolve_activity_filters(
        operation=operation,
        origin=origin,
        kind=kind,
    )

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    bound_from = _parse_bound(date_from)
    bound_to = _parse_bound(date_to, end_of_day=True)
    actor_system, actor_user_id = parse_actor_param(actor)

    if booking_id is not None:
        qs = _audit_queryset(
            allowed_ports=allowed_ports,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            actions=filters["audit_actions"],
            source=filters["source_filter"],
            exclude_sources=filters["exclude_sources"],
            lta_agreement_only=filters["lta_agreement_only"],
            booking_id=booking_id,
        )
        count = qs.count()
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])
        return {
            "count": count,
            "page": page,
            "page_size": page_size,
            "results": [_single_item(entry) for entry in rows],
        }

    items: list[dict[str, Any]] = []

    if filters["include_single"]:
        for entry in _audit_queryset(
            allowed_ports=allowed_ports,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            actions=filters["audit_actions"],
            source=filters["source_filter"],
            exclude_sources=filters["exclude_sources"],
            lta_agreement_only=filters["lta_agreement_only"],
        )[:500]:
            items.append(_single_item(entry))

    if filters["include_bulk"]:
        for batch in _batch_queryset(
            allowed_ports=allowed_ports,
            user=user,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            kind=filters["batch_kind"],
        )[:500]:
            items.append(_bulk_item(batch))

    items.sort(key=lambda x: x["occurred_at"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": page_items,
    }


def build_import_batch_detail(
    batch: BookingImportBatch,
    *,
    allowed_ports: list[int] | None,
) -> dict[str, Any]:
    bookings_qs = Booking.objects.filter(id__in=batch.created_booking_ids).only(
        "id",
        "booking_code",
        "port_id",
    )
    if allowed_ports is not None:
        bookings_qs = bookings_qs.filter(port_id__in=allowed_ports)

    created = [
        {"id": b.id, "booking_code": b.booking_code}
        for b in bookings_qs.order_by("booking_code")
    ]

    return {
        "id": batch.id,
        "label": batch.label,
        "source": batch.source,
        "status": batch.status,
        "created_at": batch.created_at,
        "finished_at": batch.finished_at,
        "user_display": _user_display(batch.created_by),
        "requested_count": batch.requested_count,
        "created_count": batch.created_count,
        "failed_count": batch.failed_count,
        "not_created_count": max(
            0, len(batch.retry_rows or []) - batch.failed_count
        ),
        "created": created,
        "failures": batch.failures or [],
        "retry_rows": batch.retry_rows or [],
        "retry_count": len(batch.retry_rows or []),
    }
