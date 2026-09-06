"""Get-or-create and assign reusable booking tags."""

from __future__ import annotations

from django.db import transaction

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


@transaction.atomic
def set_import_batch_tag(
    batch: BookingImportBatch,
    *,
    tag_name: str | None,
    user=None,
    allowed_ports: list[int] | None = None,
    clear: bool = False,
) -> BookingTag | None:
    """Create/assign or clear tag on an import batch and its created bookings."""
    if clear or not normalize_tag_name(tag_name):
        tag = None
    else:
        tag = get_or_create_tag(tag_name, user=user)
    batch.tag = tag
    batch.save(update_fields=["tag"])
    assign_tag_to_bookings(
        list(batch.created_booking_ids or []),
        tag,
        allowed_ports=allowed_ports,
    )
    return tag


@transaction.atomic
def set_run_batch_tag(
    batch: BookingRunBatch,
    *,
    tag_name: str | None,
    user=None,
    allowed_ports: list[int] | None = None,
    clear: bool = False,
) -> BookingTag | None:
    """Create/assign or clear tag on a mass-update run and its bookings."""
    if batch.kind != BookingRunBatch.Kind.MASS_UPDATE:
        raise ValueError("Solo la actualización masiva admite tags.")
    if clear or not normalize_tag_name(tag_name):
        tag = None
    else:
        tag = get_or_create_tag(tag_name, user=user)
    batch.tag = tag
    batch.save(update_fields=["tag"])
    assign_tag_to_bookings(
        list(batch.booking_ids or []),
        tag,
        allowed_ports=allowed_ports,
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
