"""Unified booking activity feed (single audits + import/run batches)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import BookingAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.audit.utils.friendly_changes import enrich_booking_audit_changes
from apps.bookings.models import Booking, BookingImportBatch, BookingRunBatch

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

FIELD_LABELS = {
    "port_id": "Puerto",
    "shipping_line_id": "Naviera",
    "vessel_id": "Barco",
    "call_date": "Fecha",
    "eta": "ETA",
    "etd": "ETD",
    "position_id": "Posición",
    "status": "Estado",
    "notes": "Notas",
    "long_term_agreement": "Acuerdo LTA",
    "long_term_agreement_id": "Acuerdo LTA",
    "tag_id": "Tag",
}


def _norm(value: str | None, allowed: tuple[str, ...], default: str) -> str:
    lowered = (value or default).lower()
    return lowered if lowered in allowed else default


def _legacy_kind_filters(kind: str) -> dict[str, Any]:
    """Map deprecated kind param to operation/origin/include flags."""
    if kind == "single":
        return {"include_bulk": False, "include_run": False}
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
    include_run = True
    audit_actions: tuple[str, ...] | None = None
    source_filter: str | None = None
    exclude_sources: tuple[str, ...] = ()
    lta_agreement_only = False
    batch_kind: str | None = None
    run_kinds: tuple[str, ...] | None = None

    legacy = _legacy_kind_filters(kind) if kind and kind not in ("all", "") else {}
    if legacy.get("include_single") is False:
        include_single = False
    if legacy.get("include_bulk") is False:
        include_bulk = False
    if legacy.get("include_run") is False:
        include_run = False
    if legacy.get("operation"):
        operation = legacy["operation"]
    if legacy.get("origin"):
        origin = legacy["origin"]

    if operation == "create":
        audit_actions = CREATE_AUDIT_ACTIONS
        run_kinds = (BookingRunBatch.Kind.LTA_GENERATE,)
    elif operation == "update":
        audit_actions = UPDATE_AUDIT_ACTIONS
        include_bulk = False
        run_kinds = (
            BookingRunBatch.Kind.MASS_UPDATE,
            BookingRunBatch.Kind.LTA_AGREEMENT,
        )
    elif operation == "delete":
        audit_actions = DELETE_AUDIT_ACTIONS
        include_bulk = False
        include_run = False
    else:
        audit_actions = SINGLE_ACTIONS
        run_kinds = None  # all run kinds

    if origin == "wizard":
        include_bulk = False
        include_run = False
        if operation in ("all", "create"):
            source_filter = "wizard"
            audit_actions = _intersect_actions(audit_actions, CREATE_AUDIT_ACTIONS)
        elif operation == "update":
            audit_actions = _intersect_actions(audit_actions, BOOKING_UPDATE_ACTIONS)
            exclude_sources = ("bulk_edit", *LTA_AGREEMENT_SOURCES)
    elif origin == "lta_generate":
        include_bulk = False
        include_single = False
        include_run = True
        run_kinds = (BookingRunBatch.Kind.LTA_GENERATE,)
        audit_actions = ()
    elif origin == "mass_import":
        batch_kind = "mass_import"
        include_single = False
        include_run = False
        if operation in ("all", "create"):
            audit_actions = CREATE_AUDIT_ACTIONS
        else:
            include_bulk = False
            audit_actions = ()
    elif origin == "berthing_import":
        batch_kind = "berthing_import"
        include_single = False
        include_run = False
        if operation in ("all", "create"):
            audit_actions = CREATE_AUDIT_ACTIONS
        else:
            include_bulk = False
            audit_actions = ()
    elif origin == "lta_agreement":
        include_bulk = False
        include_single = False
        include_run = True
        run_kinds = (BookingRunBatch.Kind.LTA_AGREEMENT,)
        audit_actions = ()
    elif origin == "mass_update":
        include_bulk = False
        include_single = False
        include_run = True
        run_kinds = (BookingRunBatch.Kind.MASS_UPDATE,)
        audit_actions = ()
    elif origin == "booking_update":
        include_bulk = False
        include_run = False
        audit_actions = _intersect_actions(audit_actions, BOOKING_UPDATE_ACTIONS)
        exclude_sources = ("bulk_edit", *LTA_AGREEMENT_SOURCES)

    if operation == "create" and origin in ("lta_agreement", "booking_update"):
        include_single = False
        include_bulk = False
        include_run = False
        audit_actions = ()
    if operation == "update" and origin in (
        "lta_generate",
        "mass_import",
        "berthing_import",
    ):
        include_single = False
        include_bulk = False
        include_run = False
        audit_actions = ()
    if operation == "delete" and origin not in ("all",):
        include_single = False
        audit_actions = ()

    if operation == "all" and origin == "all":
        # Hide singles that belong to grouped runs / imports (handled below in queryset).
        pass

    return {
        "include_single": include_single,
        "include_bulk": include_bulk,
        "include_run": include_run,
        "audit_actions": audit_actions,
        "source_filter": source_filter,
        "exclude_sources": exclude_sources,
        "lta_agreement_only": lta_agreement_only,
        "batch_kind": batch_kind,
        "run_kinds": run_kinds,
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
    raw_changes = entry.changes if isinstance(entry.changes, dict) else {}
    changes = enrich_booking_audit_changes(raw_changes) or {}
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
        "batch_type": None,
        "created_count": None,
        "updated_count": None,
        "failed_count": None,
        "not_created_count": None,
        "changed_fields": None,
        "tag_id": None,
        "tag_name": None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def _bulk_item(batch: BookingImportBatch) -> dict[str, Any]:
    tag = batch.tag
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
        "batch_type": "import",
        "created_count": batch.created_count,
        "updated_count": None,
        "failed_count": batch.failed_count,
        "not_created_count": max(
            0, len(batch.retry_rows or []) - batch.failed_count
        ),
        "changed_fields": None,
        "tag_id": tag.id if tag else None,
        "tag_name": tag.name if tag else None,
        "label": batch.label,
    }


def _lta_agreement_link_counts(
    batch: BookingRunBatch,
) -> tuple[int, int]:
    """Net vinculadas / desvinculadas (churn unlink+relink counts as neither)."""
    from apps.audit.models import BookingAuditEntry

    per_booking = _collect_run_batch_booking_changes(batch.id)
    linked, unlinked = _net_lta_counts_from_booking_changes(per_booking)
    # Prefer net from audits even when both are 0 (pure churn). Meta stores event totals.
    has_audits = BookingAuditEntry.objects.filter(
        changes__run_batch_id=batch.id,
    ).exists()
    if has_audits:
        return linked, unlinked
    meta = batch.meta if isinstance(batch.meta, dict) else {}
    return int(meta.get("linked") or 0), int(meta.get("unlinked") or 0)


def _net_lta_counts_from_booking_changes(
    per_booking: dict[int, list[dict[str, Any]]],
) -> tuple[int, int]:
    """Count bookings whose net LTA delta is link vs unlink."""
    linked = 0
    unlinked = 0
    for rows in per_booking.values():
        for row in rows:
            if row.get("field") not in (
                "long_term_agreement",
                "long_term_agreement_id",
            ):
                continue
            fr = row.get("from")
            to = row.get("to")
            fr_empty = fr in (None, "", "—")
            to_empty = to in (None, "", "—")
            if fr_empty and not to_empty:
                linked += 1
            elif not fr_empty and to_empty:
                unlinked += 1
    return linked, unlinked


def _run_item(batch: BookingRunBatch) -> dict[str, Any]:
    tag = batch.tag
    field_keys = list(batch.changed_fields or [])
    field_labels = [FIELD_LABELS.get(key, key) for key in field_keys]

    linked_count: int | None = None
    unlinked_count: int | None = None

    if batch.kind == BookingRunBatch.Kind.MASS_UPDATE:
        action = "bulk_update"
        summary = (
            f"Actualización masiva: {batch.success_count} actualizadas, "
            f"{batch.failed_count} fallidas"
        )
        if field_labels:
            summary = f"{summary} · {', '.join(field_labels)}"
    elif batch.kind == BookingRunBatch.Kind.LTA_GENERATE:
        action = "bulk_lta_generate"
        summary = f"Creación LTA: {batch.success_count} creadas"
    else:
        action = "bulk_lta_agreement"
        linked_count, unlinked_count = _lta_agreement_link_counts(batch)
        if linked_count or unlinked_count:
            parts = []
            if linked_count:
                parts.append(f"{linked_count} vinculadas")
            if unlinked_count:
                parts.append(f"{unlinked_count} desvinculadas")
            summary = f"Actualización LTA: {', '.join(parts)}"
        else:
            summary = "Actualización LTA: sin cambio de vínculo"
        if field_labels:
            summary = f"{summary} · {', '.join(field_labels)}"

    return {
        "kind": "bulk",
        "action": action,
        "occurred_at": batch.created_at,
        "user_display": _user_display(batch.created_by),
        "summary": summary,
        "booking_id": None,
        "booking_code": None,
        "batch_id": batch.id,
        "batch_type": batch.kind,
        "created_count": (
            batch.success_count
            if batch.kind == BookingRunBatch.Kind.LTA_GENERATE
            else None
        ),
        "updated_count": (
            batch.success_count
            if batch.kind == BookingRunBatch.Kind.MASS_UPDATE
            else (
                (linked_count or 0) + (unlinked_count or 0)
                if batch.kind == BookingRunBatch.Kind.LTA_AGREEMENT
                else None
            )
        ),
        "failed_count": batch.failed_count,
        "not_created_count": None,
        "changed_fields": field_keys,
        "changed_field_labels": field_labels,
        "linked_count": (
            linked_count
            if batch.kind == BookingRunBatch.Kind.LTA_AGREEMENT
            else (linked_count or None)
        ),
        "unlinked_count": (
            unlinked_count
            if batch.kind == BookingRunBatch.Kind.LTA_AGREEMENT
            else (unlinked_count or None)
        ),
        "tag_id": tag.id if tag else None,
        "tag_name": tag.name if tag else None,
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
    )
    # Global feed rolls import/run batches into cards; booking detail keeps every row.
    if booking_id is None:
        qs = qs.exclude(changes__has_key="import_batch_id").exclude(
            changes__has_key="run_batch_id"
        )
    else:
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
    qs = BookingImportBatch.objects.select_related("created_by", "tag")
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


def _run_batch_queryset(
    *,
    allowed_ports: list[int] | None,
    user,
    date_from,
    date_to,
    actor_system: bool = False,
    actor_user_id: int | None = None,
    kinds: tuple[str, ...] | None = None,
):
    qs = BookingRunBatch.objects.select_related("created_by", "tag")
    if kinds is not None:
        if not kinds:
            return BookingRunBatch.objects.none()
        qs = qs.filter(kind__in=kinds)
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
    audit_qs = (
        BookingAuditEntry.objects.filter(action__in=SINGLE_ACTIONS)
        .exclude(changes__has_key="import_batch_id")
        .exclude(changes__has_key="run_batch_id")
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

    run_qs = BookingRunBatch.objects.all()
    if allowed_ports is not None:
        run_qs = run_qs.filter(created_by=user)
    run_ids = set(
        run_qs.exclude(created_by_id=None)
        .values_list("created_by_id", flat=True)
        .distinct()
    )
    has_system_run = run_qs.filter(created_by_id__isnull=True).exists()

    return {
        "results": actor_options_from_ids(audit_ids | batch_ids | run_ids),
        "has_system": has_system_audit or has_system_batch or has_system_run,
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

    if filters["include_run"]:
        for batch in _run_batch_queryset(
            allowed_ports=allowed_ports,
            user=user,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            kinds=filters["run_kinds"],
        )[:500]:
            items.append(_run_item(batch))

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


def _list_page_slice(
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, int, int]:
    """Return (page, page_size, start) clamped for list endpoints."""
    safe_page = max(1, int(page or 1))
    safe_size = min(max(1, int(page_size or 20)), 100)
    return safe_page, safe_size, (safe_page - 1) * safe_size


def build_import_batch_detail(
    batch: BookingImportBatch,
    *,
    allowed_ports: list[int] | None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    from apps.catalogs.utils.position_code import position_short_code

    bookings_qs = Booking.objects.filter(
        id__in=batch.created_booking_ids or [],
    ).select_related(
        "port",
        "vessel",
        "shipping_line",
        "position",
        "position__port",
    )
    if allowed_ports is not None:
        bookings_qs = bookings_qs.filter(port_id__in=allowed_ports)

    bookings_qs = bookings_qs.order_by("call_date", "booking_code")
    created_total = bookings_qs.count()
    safe_page, safe_size, start = _list_page_slice(page=page, page_size=page_size)

    created: list[dict[str, Any]] = []
    for booking in bookings_qs[start : start + safe_size]:
        position_code = None
        if booking.position_id and booking.position is not None:
            port_code = (
                booking.position.port.code
                if booking.position.port_id
                else (booking.port.code if booking.port_id else "")
            )
            position_code = (
                position_short_code(port_code, booking.position.code)
                if port_code
                else booking.position.code
            )
        created.append(
            {
                "id": booking.id,
                "booking_code": booking.booking_code,
                "call_date": (
                    booking.call_date.isoformat() if booking.call_date else None
                ),
                "port_name": booking.port.name if booking.port_id else None,
                "vessel_name": booking.vessel.name if booking.vessel_id else None,
                "shipping_line_name": (
                    booking.shipping_line.name if booking.shipping_line_id else None
                ),
                "position_code": position_code,
                "status": booking.status,
                "status_label": STATUS_DISPLAY.get(
                    booking.status, booking.status or "—"
                ),
            }
        )
    tag = batch.tag

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
        "created_total": created_total,
        "created_page": safe_page,
        "created_page_size": safe_size,
        "failures": batch.failures or [],
        "retry_rows": batch.retry_rows or [],
        "retry_count": len(batch.retry_rows or []),
        "tag_id": tag.id if tag else None,
        "tag_name": tag.name if tag else None,
        "supports_tag": True,
    }


def _display_change_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return str(value)


def _friendly_position_code(code: str | None) -> str | None:
    if not code:
        return None
    text = str(code).strip()
    if not text:
        return None
    # Catalog codes are usually "{port}-{short}" (e.g. puerto_plata-E1).
    if "-" in text:
        return text.split("-", 1)[1]
    return text


STATUS_DISPLAY = {
    "nr": "Solicitada",
    "h": "En evaluación",
    "co": "Confirmada",
    "cl": "Confirmada LTA",
    "lta": "LTA",
    "ltd": "Long Term Deployment",
    "r": "Real",
    "c": "Cancelada",
}


def _side_label(raw: dict, *, side: str, field: str) -> str:
    """Prefer human labels (name / short code) over raw FK ids."""
    if side == "from":
        code = raw.get("from_code")
        name = raw.get("from_name") or raw.get("from_label")
        value = raw.get("from", raw.get("old"))
    else:
        code = raw.get("to_code")
        name = raw.get("to_name") or raw.get("to_label")
        value = raw.get("to", raw.get("new"))

    if field in ("position_id", "position"):
        if code:
            return _friendly_position_code(str(code)) or "—"
        if name not in (None, ""):
            return _friendly_position_code(str(name)) or str(name)
        return "—"

    # Ports / lines / vessels: operator-facing name, never catalog slug alone.
    if field in (
        "port_id",
        "shipping_line_id",
        "vessel_id",
        "long_term_agreement_id",
        "tag_id",
    ):
        if name not in (None, ""):
            return str(name)
        if code not in (None, ""):
            return str(code)
        if field == "long_term_agreement_id" and value not in (None, ""):
            return "—"
        return "—" if isinstance(value, int) or (
            isinstance(value, str) and value.isdigit()
        ) else _display_change_value(value)

    if name not in (None, ""):
        return str(name)
    if code not in (None, ""):
        return str(code)
    if field == "status" and isinstance(value, str):
        return STATUS_DISPLAY.get(value, value)
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return "—"
    return _display_change_value(value)


def _extract_change_sides(raw: Any, *, field: str) -> tuple[str, str] | None:
    if not isinstance(raw, dict):
        return None
    if not (
        "from" in raw
        or "to" in raw
        or "old" in raw
        or "new" in raw
        or "from_code" in raw
        or "to_code" in raw
    ):
        return None
    return _side_label(raw, side="from", field=field), _side_label(
        raw, side="to", field=field
    )


_SKIP_CHANGE_KEYS = frozenset(
    {
        "source",
        "entity",
        "context",
        "run_batch_id",
        "import_batch_id",
        "acknowledge_combined_red",
    }
)


def _field_change_rows_from_changes(changes: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, raw in changes.items():
        if key in _SKIP_CHANGE_KEYS:
            continue
        sides = _extract_change_sides(raw, field=key)
        if sides is None:
            continue
        from_text, to_text = sides
        rows.append(
            {
                "field": key,
                "label": FIELD_LABELS.get(key, key),
                "from": from_text,
                "to": to_text,
            }
        )
    rows.sort(key=lambda row: row["label"])
    return rows


def _collect_run_batch_booking_changes(
    batch_id: int,
) -> dict[int, list[dict[str, Any]]]:
    """Per-booking from→to field deltas for a run batch.

    Several audits on the same field are collapsed to the net from→to.
    Unlink then re-link of the same agreement is omitted (no real update).
    """
    from apps.audit.models import BookingAuditEntry

    # booking_id -> field -> chronological side pairs
    chains: dict[int, dict[str, list[tuple[str, str]]]] = {}
    labels: dict[str, str] = {}

    for entry in (
        BookingAuditEntry.objects.filter(changes__run_batch_id=batch_id)
        .exclude(booking_id__isnull=True)
        .only("booking_id", "changes", "created_at")
        .order_by("created_at", "id")
        .iterator(chunk_size=500)
    ):
        booking_id = entry.booking_id
        if booking_id is None:
            continue
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        changes = enrich_booking_audit_changes(changes) or {}
        rows = _field_change_rows_from_changes(changes)
        if not rows:
            continue
        by_field = chains.setdefault(booking_id, {})
        for row in rows:
            field = row["field"]
            labels[field] = row["label"]
            by_field.setdefault(field, []).append((row["from"], row["to"]))

    by_booking: dict[int, list[dict[str, Any]]] = {}
    for booking_id, fields in chains.items():
        rows: list[dict[str, Any]] = []
        for field, sides in fields.items():
            if not sides:
                continue
            net_from = sides[0][0]
            net_to = sides[-1][1]
            # Unlink then re-link (same agreement) → omit; not an update.
            if net_from == net_to:
                continue
            rows.append(
                {
                    "field": field,
                    "label": labels.get(field, FIELD_LABELS.get(field, field)),
                    "from": net_from,
                    "to": net_to,
                }
            )
        if rows:
            rows.sort(key=lambda row: row["label"])
            by_booking[booking_id] = rows
    return by_booking


def build_run_batch_detail(
    batch: BookingRunBatch,
    *,
    allowed_ports: list[int] | None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    from apps.catalogs.utils.position_code import position_short_code

    bookings_qs = Booking.objects.filter(
        id__in=batch.booking_ids or [],
    ).select_related(
        "port",
        "vessel",
        "shipping_line",
        "position",
        "position__port",
    )
    if allowed_ports is not None:
        bookings_qs = bookings_qs.filter(port_id__in=allowed_ports)

    per_booking = _collect_run_batch_booking_changes(batch.id)

    linked_count = 0
    unlinked_count = 0
    success_count = int(batch.success_count or 0)
    if batch.kind == BookingRunBatch.Kind.LTA_AGREEMENT:
        linked_count, unlinked_count = _net_lta_counts_from_booking_changes(
            per_booking
        )
        # List only bookings with a real net vínculo change (no churn rows).
        changed_ids = list(per_booking.keys())
        bookings_qs = bookings_qs.filter(id__in=changed_ids or [-1])
        success_count = linked_count + unlinked_count

    bookings_qs = bookings_qs.order_by("call_date", "booking_code")
    bookings_total = bookings_qs.count()
    safe_page, safe_size, start = _list_page_slice(page=page, page_size=page_size)

    fallback_changes: list[dict[str, Any]] = []
    if batch.changed_fields and batch.kind != BookingRunBatch.Kind.LTA_AGREEMENT:
        fallback_changes = [
            {
                "field": key,
                "label": FIELD_LABELS.get(key, key),
                "from": "—",
                "to": "—",
            }
            for key in batch.changed_fields
        ]

    bookings = []
    for booking in bookings_qs[start : start + safe_size]:
        changes = per_booking.get(booking.id) or fallback_changes
        position_code = None
        if booking.position_id and booking.position is not None:
            port_code = (
                booking.position.port.code
                if booking.position.port_id
                else (booking.port.code if booking.port_id else "")
            )
            position_code = (
                position_short_code(port_code, booking.position.code)
                if port_code
                else booking.position.code
            )
        bookings.append(
            {
                "id": booking.id,
                "booking_code": booking.booking_code,
                "call_date": (
                    booking.call_date.isoformat() if booking.call_date else None
                ),
                "port_name": booking.port.name if booking.port_id else None,
                "vessel_name": booking.vessel.name if booking.vessel_id else None,
                "shipping_line_name": (
                    booking.shipping_line.name if booking.shipping_line_id else None
                ),
                "position_code": position_code,
                "status": booking.status,
                "status_label": STATUS_DISPLAY.get(
                    booking.status, booking.status or "—"
                ),
                "field_changes": changes,
            }
        )
    tag = batch.tag
    supports_tag = batch.kind == BookingRunBatch.Kind.MASS_UPDATE

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rows in per_booking.values():
        for row in rows:
            bucket_key = (row["field"], row["from"], row["to"])
            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "field": row["field"],
                    "label": row["label"],
                    "from": row["from"],
                    "to": row["to"],
                    "count": 0,
                }
            buckets[bucket_key]["count"] += 1
    field_changes = list(buckets.values())
    field_changes.sort(key=lambda row: (row["label"], row["from"], row["to"]))
    if not field_changes and fallback_changes:
        field_changes = [
            {**row, "count": success_count} for row in fallback_changes
        ]

    return {
        "id": batch.id,
        "kind": batch.kind,
        "label": batch.label,
        "created_at": batch.created_at,
        "user_display": _user_display(batch.created_by),
        "success_count": success_count,
        "failed_count": batch.failed_count,
        "changed_fields": list(batch.changed_fields or []),
        "changed_field_labels": [
            FIELD_LABELS.get(key, key) for key in (batch.changed_fields or [])
        ],
        "field_changes": field_changes,
        "linked_count": linked_count,
        "unlinked_count": unlinked_count,
        "bookings": bookings,
        "bookings_total": bookings_total,
        "bookings_page": safe_page,
        "bookings_page_size": safe_size,
        "failures": batch.failures or [],
        "meta": batch.meta or {},
        "tag_id": tag.id if tag else None,
        "tag_name": tag.name if tag else None,
        "supports_tag": supports_tag,
    }
