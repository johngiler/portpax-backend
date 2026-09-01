"""Create bookings from resolved ITM mass-import rows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import BookingImportBatch, BookingStatus
from apps.bookings.services.booking.batch_create import (
    BookingBatchCreateError,
    create_booking_batch,
)


def _parse_time(value: str | None):
    if not value:
        return None
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _normalize_retry_row(
    row: dict[str, Any],
    *,
    extra_issues: list[str] | None = None,
) -> dict[str, Any]:
    """Normalize a preview/create row into a BulkImportPreviewRow-shaped snapshot."""
    row_id = str(row.get("id") or row.get("row_number") or "")
    try:
        row_number = int(row.get("row_number") or 0)
    except (TypeError, ValueError):
        row_number = 0

    issues = _as_str_list(row.get("issues"))
    if extra_issues:
        for issue in extra_issues:
            if issue and issue not in issues:
                issues.append(issue)

    call_date = row.get("call_date")
    eta = row.get("eta")
    etd = row.get("etd")

    port_id = row.get("port_id")
    vessel_id = row.get("vessel_id")
    shipping_line_id = row.get("shipping_line_id")
    position_id = row.get("position_id")
    try:
        port_id = int(port_id) if port_id is not None and port_id != "" else None
    except (TypeError, ValueError):
        port_id = None
    try:
        vessel_id = int(vessel_id) if vessel_id is not None and vessel_id != "" else None
    except (TypeError, ValueError):
        vessel_id = None
    try:
        shipping_line_id = (
            int(shipping_line_id)
            if shipping_line_id is not None and shipping_line_id != ""
            else None
        )
    except (TypeError, ValueError):
        shipping_line_id = None
    try:
        position_id = (
            int(position_id) if position_id is not None and position_id != "" else None
        )
    except (TypeError, ValueError):
        position_id = None

    selectable = bool(row.get("selectable"))
    if issues:
        # Create failures or deferred invalid rows stay non-selectable until re-resolved.
        if extra_issues:
            selectable = False
    elif row.get("selectable") is None:
        selectable = bool(port_id and vessel_id and shipping_line_id and call_date and eta and etd)

    return {
        "id": row_id or f"retry-{row_number}",
        "row_number": row_number,
        "ship": str(row.get("ship") or row.get("vessel_name") or ""),
        "port_raw": str(row.get("port_raw") or row.get("port") or row.get("port_name") or ""),
        "vendor_name": str(row.get("vendor_name") or ""),
        "call_type": str(row.get("call_type") or ""),
        "call_date": str(call_date) if call_date else None,
        "eta": str(eta)[:8] if eta else None,
        "etd": str(etd)[:8] if etd else None,
        "port_id": port_id,
        "port_name": row.get("port_name"),
        "port_code": row.get("port_code"),
        "vessel_id": vessel_id,
        "vessel_name": row.get("vessel_name") or row.get("ship"),
        "shipping_line_id": shipping_line_id,
        "shipping_line_name": row.get("shipping_line_name"),
        "suggested_status": str(row.get("suggested_status") or "h").lower(),
        "position_id": position_id,
        "position_code": row.get("position_code"),
        "claim_lta_space": bool(
            row.get("claim_lta_space") or row.get("replace_lta")
        ),
        "lta_space_candidate": (
            row.get("lta_space_candidate")
            if "lta_space_candidate" in row
            else row.get("lta_replace_candidate")
        ),
        "issues": issues,
        "warnings": _as_str_list(row.get("warnings")),
        "selectable": selectable,
        "selected_default": False,
    }


def _failure_payload(row: dict[str, Any], row_id: Any, detail: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "row_id": row_id,
        "detail": detail,
    }
    ship = row.get("ship") or row.get("vessel_name")
    port = row.get("port") or row.get("port_raw") or row.get("port_code") or row.get("port_name")
    call_date = row.get("call_date")
    if ship:
        payload["ship"] = str(ship)
    if port:
        payload["port"] = str(port)
    if call_date:
        payload["call_date"] = str(call_date)
    return payload


def _claim_lta_space_booking(
    *,
    candidate_id: int,
    vessel_id: int,
    shipping_line_id: int,
    eta,
    etd,
    preferred_position_id: int | None,
    created_by=None,
):
    """
    Claim reserved LTA capacity in place: update vessel/ETA/ETD/position and
    move status LTA → CL (Confirmed LTA). Does not cancel or create a new row.
    """
    from apps.bookings.models import Booking, BookingStatus
    from apps.bookings.services.booking.status import (
        BookingStatusError,
        BookingValidationError,
        update_booking_operational,
        update_booking_status,
    )
    from apps.audit.services.record import record_booking_audit
    from apps.catalogs.models import Vessel

    booking = (
        Booking.objects.select_related("vessel", "position", "port", "shipping_line")
        .filter(pk=candidate_id, status=BookingStatus.LTA)
        .first()
    )
    if booking is None:
        raise BookingBatchCreateError(
            "El espacio LTA a reclamar ya no está disponible.",
            "claim_lta_space",
        )
    if booking.shipping_line_id != shipping_line_id:
        raise BookingBatchCreateError(
            "El espacio LTA pertenece a otra naviera.",
            "claim_lta_space",
        )

    vessel = Vessel.objects.filter(pk=vessel_id, is_active=True).first()
    if vessel is None:
        raise BookingBatchCreateError("Barco no válido.", "vessel_id")
    if vessel.shipping_line_id != shipping_line_id:
        raise BookingBatchCreateError(
            "El barco no pertenece a la naviera del espacio LTA.",
            "vessel_id",
        )

    # Unique port/vessel/date — another live booking for the new vessel blocks claim.
    clash = (
        Booking.objects.filter(
            port_id=booking.port_id,
            vessel_id=vessel_id,
            call_date=booking.call_date,
        )
        .exclude(pk=booking.pk)
        .exclude(status=BookingStatus.C)
        .first()
    )
    if clash is not None:
        raise BookingBatchCreateError(
            "Ya existe una reserva para este barco/puerto/fecha; "
            "no se puede reclamar el LTA con ese barco.",
            "vessel_id",
        )

    changes: dict[str, Any] = {"claimed_lta_space": True}
    vessel_update_fields = ["updated_at"]
    if booking.vessel_id != vessel_id:
        changes["vessel_id"] = {
            "from": booking.vessel_id,
            "to": vessel_id,
            "from_name": booking.vessel.name if booking.vessel_id else None,
            "to_name": vessel.name,
        }
        booking.vessel = vessel
        vessel_update_fields.append("vessel")

    if len(vessel_update_fields) > 1:
        booking.save(update_fields=vessel_update_fields)
        record_booking_audit(
            booking,
            action="operational_update",
            summary="Reclamo de espacio LTA: actualización de barco",
            changes={k: v for k, v in changes.items() if k != "claimed_lta_space"},
            user=created_by,
        )

    position_id = preferred_position_id
    if position_id is None:
        position_id = booking.position_id

    try:
        update_booking_operational(
            booking,
            user=created_by,
            position_id=position_id,
            eta=eta,
            etd=etd,
        )
        booking.refresh_from_db()
        update_booking_status(
            booking,
            BookingStatus.CL,
            user=created_by,
            # Placeholder LTA rows may have no LongTermAgreement catalog match;
            # claiming the reserved slot must still move LTA → CL.
            require_lta_agreement=False,
        )
    except BookingStatusError as exc:
        raise BookingBatchCreateError(str(exc), "claim_lta_space") from exc
    except BookingValidationError as exc:
        msgs = [
            (e.get("message") if isinstance(e, dict) else str(e))
            for e in (exc.errors or [])
        ]
        detail = "; ".join(m for m in msgs if m) or str(exc)
        raise BookingBatchCreateError(detail, "claim_lta_space") from exc

    booking.refresh_from_db()
    record_booking_audit(
        booking,
        action="operational_update",
        summary="Espacio LTA reclamado (Confirmada LTA)",
        changes=changes,
        user=created_by,
    )
    return booking


def create_from_resolved_rows(
    rows: list[dict[str, Any]],
    *,
    created_by=None,
    source: str = BookingImportBatch.Source.FILE,
    label: str = "",
    deferred_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create one booking per selected resolved row.
    When claim_lta_space is set, updates the existing LTA in place to CL.
    Persists a BookingImportBatch with successes, failures, and retry_rows
    (failed creates + deferred/not-selectable/not-selected preview rows).
    """
    if source not in BookingImportBatch.Source.values:
        source = BookingImportBatch.Source.FILE
    batch_label = (label or "").strip() or (
        "Pegado desde Excel"
        if source == BookingImportBatch.Source.PASTE
        else "Importación masiva"
    )

    deferred = deferred_rows or []
    batch = BookingImportBatch.objects.create(
        created_by=created_by,
        source=source,
        label=batch_label,
        requested_count=len(rows) + len(deferred),
        status=BookingImportBatch.Status.COMPLETED,
    )

    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    created_booking_ids: list[int] = []
    created_port_ids: set[int] = set()
    retry_rows: list[dict[str, Any]] = []
    audit_changes = {
        "import_batch_id": batch.id,
        "source": "mass_import",
    }

    for row in deferred:
        if isinstance(row, dict):
            retry_rows.append(_normalize_retry_row(row))

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id") or row.get("row_number")
        try:
            port_id = int(row["port_id"])
            shipping_line_id = int(row["shipping_line_id"])
            vessel_id = int(row["vessel_id"])
            call_date = date.fromisoformat(str(row["call_date"]))
            eta = _parse_time(row.get("eta"))
            etd = _parse_time(row.get("etd"))
            if eta is None or etd is None:
                raise BookingBatchCreateError("ETA/ETD inválidos.", "eta")

            from apps.bookings.services.booking.batch_create import BULK_CREATE_STATUSES

            status_raw = str(row.get("suggested_status") or BookingStatus.H).lower()
            initial_status = (
                status_raw if status_raw in BULK_CREATE_STATUSES else BookingStatus.H
            )

            preferred_position_id = None
            raw_pos = row.get("position_id")
            if raw_pos is not None and raw_pos != "":
                preferred_position_id = int(raw_pos)

            candidate = (
                row.get("lta_space_candidate")
                or row.get("lta_replace_candidate")
                or {}
            )
            candidate_id = None
            if isinstance(candidate, dict) and candidate.get("id") is not None:
                candidate_id = int(candidate["id"])
            claim = bool(row.get("claim_lta_space") or row.get("replace_lta"))

            with transaction.atomic():
                if claim and candidate_id:
                    booking = _claim_lta_space_booking(
                        candidate_id=candidate_id,
                        vessel_id=vessel_id,
                        shipping_line_id=shipping_line_id,
                        eta=eta,
                        etd=etd,
                        preferred_position_id=preferred_position_id,
                        created_by=created_by,
                    )
                else:
                    bookings = create_booking_batch(
                        port_id=port_id,
                        shipping_line_id=shipping_line_id,
                        vessel_id=vessel_id,
                        call_dates=[call_date],
                        notes="",
                        created_by=created_by,
                        eta=eta,
                        etd=etd,
                        preferred_position_id=preferred_position_id,
                        audit_changes=audit_changes,
                        status=initial_status,
                    )
                    booking = bookings[0]

            created_booking_ids.append(booking.id)
            created_port_ids.add(port_id)
            created.append(
                {
                    "id": row_id,
                    "booking_id": booking.id,
                    "booking_code": booking.booking_code,
                }
            )
        except (KeyError, TypeError, ValueError, BookingBatchCreateError) as exc:
            detail = str(exc)
            failures.append(_failure_payload(row, row_id, detail))
            retry_rows.append(_normalize_retry_row(row, extra_issues=[detail]))

    batch.created_count = len(created)
    batch.failed_count = len(failures)
    batch.created_booking_ids = created_booking_ids
    batch.failures = failures
    batch.retry_rows = retry_rows
    batch.finished_at = timezone.now()
    batch.save(
        update_fields=[
            "created_count",
            "failed_count",
            "created_booking_ids",
            "failures",
            "retry_rows",
            "finished_at",
            "status",
            "requested_count",
        ]
    )

    if created:
        from apps.notifications.models import Notification
        from apps.notifications.services.booking import notify_bookings_bulk_created

        port_id = next(iter(created_port_ids)) if len(created_port_ids) == 1 else None
        notify_bookings_bulk_created(
            count=len(created),
            port_id=port_id,
            port_ids=created_port_ids if len(created_port_ids) > 1 else None,
            batch_id=batch.id,
            artifact=Notification.Artifact.MASS_IMPORT,
            actor=created_by,
        )

    return {
        "batch_id": batch.id,
        "created_count": len(created),
        "failed_count": len(failures),
        "created": created,
        "failures": failures,
        "retry_count": len(retry_rows),
    }
