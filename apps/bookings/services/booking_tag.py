"""Get-or-create and assign reusable booking tags."""

from __future__ import annotations

from django.db import transaction

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingImportBatch, BookingRunBatch, BookingTag


def normalize_tag_name(raw: str | None) -> str:
    return " ".join((raw or "").strip().split())


def get_or_create_tag(
    name: str | None,
    *,
    user=None,
) -> BookingTag | None:
    """Return existing tag by case-insensitive name, or create. Empty → None."""
    cleaned = normalize_tag_name(name)
    if not cleaned:
        return None
    existing = BookingTag.objects.filter(name__iexact=cleaned).first()
    if existing:
        return existing
    return BookingTag.objects.create(
        name=cleaned,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def suggest_tags(query: str = "", *, limit: int = 20) -> list[BookingTag]:
    qs = BookingTag.objects.all()
    cleaned = normalize_tag_name(query)
    if cleaned:
        qs = qs.filter(name__icontains=cleaned)
    return list(qs.order_by("name")[: max(1, min(limit, 50))])


def record_booking_tag_audit(
    booking: Booking,
    *,
    previous: BookingTag | None,
    next_tag: BookingTag | None,
    user=None,
    request=None,
    audit_extra: dict | None = None,
    previous_name: str | None = None,
    next_name: str | None = None,
) -> None:
    prev_id = previous.id if previous else None
    next_id = next_tag.id if next_tag else None
    prev_label = previous_name
    if prev_label is None:
        prev_label = previous.name if previous else None
    next_label = next_name
    if next_label is None:
        next_label = next_tag.name if next_tag else None
    # Same FK with same display name → no-op (incl. rename no-op).
    if prev_id == next_id and (prev_label or "") == (next_label or ""):
        return
    if prev_id == next_id and prev_label != next_label:
        summary = f"Tag: {prev_label} → {next_label}"
    elif next_tag and previous:
        summary = f"Tag: {prev_label} → {next_label}"
    elif next_tag:
        summary = f"Tag asignado: {next_label}"
    else:
        summary = f"Tag quitado: {prev_label}" if prev_label else "Tag quitado"
    changes = {
        "tag_id": {
            "from": prev_id,
            "to": next_id,
            "from_name": prev_label,
            "to_name": next_label,
        }
    }
    if audit_extra:
        changes = {**changes, **audit_extra}
    record_booking_audit(
        booking,
        action="operational_update",
        summary=summary,
        changes=changes,
        user=user,
        request=request,
    )


def record_tag_rename_on_bookings(
    tag: BookingTag,
    *,
    previous_name: str,
    next_name: str,
    user=None,
    request=None,
) -> int:
    """Fan-out rename audit to every booking still linked to this tag."""
    if (previous_name or "").strip() == (next_name or "").strip():
        return 0
    count = 0
    for booking in Booking.objects.filter(tag_id=tag.pk).iterator(chunk_size=200):
        record_booking_tag_audit(
            booking,
            previous=tag,
            next_tag=tag,
            previous_name=previous_name,
            next_name=next_name,
            user=user,
            request=request,
            audit_extra={"source": "tag_rename"},
        )
        count += 1
    return count


def assign_tag_to_bookings(
    booking_ids: list[int],
    tag: BookingTag | None,
    *,
    allowed_ports: list[int] | None = None,
) -> int:
    """Set Booking.tag for the given ids. Returns updated count."""
    if not booking_ids:
        return 0
    qs = Booking.objects.filter(id__in=booking_ids)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    return qs.update(tag=tag)


def assign_tag_to_bookings_tracked(
    booking_ids: list[int],
    tag: BookingTag | None,
    *,
    allowed_ports: list[int] | None = None,
    user=None,
    request=None,
    audit_extra: dict | None = None,
    create_run_batch: bool = False,
    run_batch_label: str = "Actualización masiva",
) -> tuple[int, BookingRunBatch | None]:
    """
    Assign tag and audit each real change.

    When create_run_batch=True (historical card assign), also creates a mass_update
    run card for the history feed.
    """
    if not booking_ids:
        return 0, None

    qs = Booking.objects.filter(id__in=booking_ids).select_related("tag", "port")
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)

    changed: list[tuple[Booking, BookingTag | None]] = []
    for booking in qs:
        prev = booking.tag
        prev_id = prev.id if prev else None
        next_id = tag.id if tag else None
        if prev_id != next_id:
            changed.append((booking, prev))

    if not changed:
        return 0, None

    changed_ids = [b.id for b, _ in changed]
    assign_tag_to_bookings(changed_ids, tag, allowed_ports=allowed_ports)

    run_batch = None
    extra = dict(audit_extra or {})
    if create_run_batch:
        run_batch = BookingRunBatch.objects.create(
            kind=BookingRunBatch.Kind.MASS_UPDATE,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            label=run_batch_label,
            tag=tag,
            booking_ids=changed_ids,
            success_count=len(changed_ids),
            failed_count=0,
            changed_fields=["tag_id"],
            failures=[],
            meta={"source": "historical_tag_assign"},
        )
        extra["run_batch_id"] = run_batch.id
        extra["source"] = "historical_tag_assign"

    for booking, previous in changed:
        booking.tag = tag
        record_booking_tag_audit(
            booking,
            previous=previous,
            next_tag=tag,
            user=user,
            request=request,
            audit_extra=extra or None,
        )

    return len(changed_ids), run_batch


@transaction.atomic
def set_import_batch_tag(
    batch: BookingImportBatch,
    *,
    tag_name: str | None,
    user=None,
    request=None,
    allowed_ports: list[int] | None = None,
    clear: bool = False,
) -> BookingTag | None:
    """Assign/clear tag on import-batch bookings and open a mass-update history card."""
    if clear or not normalize_tag_name(tag_name):
        tag = None
    else:
        tag = get_or_create_tag(tag_name, user=user)
    batch.tag = tag
    batch.save(update_fields=["tag"])
    assign_tag_to_bookings_tracked(
        list(batch.created_booking_ids or []),
        tag,
        allowed_ports=allowed_ports,
        user=user,
        request=request,
        create_run_batch=True,
        run_batch_label="Actualización masiva",
    )
    return tag


@transaction.atomic
def set_run_batch_tag(
    batch: BookingRunBatch,
    *,
    tag_name: str | None,
    user=None,
    request=None,
    allowed_ports: list[int] | None = None,
    clear: bool = False,
) -> BookingTag | None:
    """Assign/clear tag on mass-update bookings and open a new mass-update card."""
    if batch.kind != BookingRunBatch.Kind.MASS_UPDATE:
        raise ValueError("Solo la actualización masiva admite tags.")
    if clear or not normalize_tag_name(tag_name):
        tag = None
    else:
        tag = get_or_create_tag(tag_name, user=user)
    batch.tag = tag
    batch.save(update_fields=["tag"])
    assign_tag_to_bookings_tracked(
        list(batch.booking_ids or []),
        tag,
        allowed_ports=allowed_ports,
        user=user,
        request=request,
        create_run_batch=True,
        run_batch_label="Actualización masiva",
    )
    return tag


def delete_unused_tag(tag: BookingTag) -> bool:
    """Delete tag if no bookings/batches reference it. Returns whether deleted."""
    still_used = (
        Booking.objects.filter(tag=tag).exists()
        or BookingImportBatch.objects.filter(tag=tag).exists()
        or BookingRunBatch.objects.filter(tag=tag).exists()
    )
    if still_used:
        return False
    tag.delete()
    return True


def booking_ids_for_tag(tag: BookingTag) -> list[int]:
    return list(
        Booking.objects.filter(tag=tag).order_by("id").values_list("id", flat=True)
    )


def find_tag_by_id_or_name(
    *,
    tag_id: int | None = None,
    tag_name: str | None = None,
    user=None,
    create: bool = True,
) -> BookingTag | None:
    if tag_id is not None:
        try:
            return BookingTag.objects.get(pk=int(tag_id))
        except (TypeError, ValueError, BookingTag.DoesNotExist):
            return None
    if create:
        return get_or_create_tag(tag_name, user=user)
    cleaned = normalize_tag_name(tag_name)
    if not cleaned:
        return None
    return BookingTag.objects.filter(name__iexact=cleaned).first()
