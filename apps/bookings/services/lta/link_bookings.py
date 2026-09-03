"""Link / unlink bookings to a LongTermAgreement by matching rules."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, LongTermAgreement
from apps.bookings.services.lta.matching import (
    agreement_covers_position,
    agreement_covers_validity,
    agreement_covers_vessel,
    find_best_matching_agreement,
)
from apps.bookings.services.lta.date_exceptions import agreement_covers_call_date
from apps.bookings.services.validation.conflicts import (
    refresh_related_booking_conflicts,
)


def agreement_covers_booking(agreement: LongTermAgreement, booking: Booking) -> bool:
    if not agreement_covers_validity(agreement, booking.call_date):
        return False
    if not agreement_covers_call_date(agreement, booking.call_date):
        return False
    if not agreement_covers_vessel(agreement, booking.vessel):
        return False
    if not agreement_covers_position(
        agreement,
        booking.position,
        require_position=False,
    ):
        return False
    return True


def unlink_agreement_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
    booking_ids: set[int] | None = None,
) -> dict:
    """Clear long_term_agreement FK on linked bookings (all or a subset)."""
    qs = Booking.objects.filter(long_term_agreement_id=agreement.pk).select_related(
        "vessel",
        "position",
        "shipping_line",
        "port",
    )
    if booking_ids is not None:
        qs = qs.filter(pk__in=booking_ids)
    bookings = list(qs)
    if not bookings:
        return {
            "unlinked": 0,
            "dry_run": dry_run,
            "agreement_code": agreement.code,
        }

    if dry_run:
        return {
            "unlinked": len(bookings),
            "dry_run": True,
            "agreement_code": agreement.code,
        }

    now = timezone.now()
    code = agreement.code
    for booking in bookings:
        booking.long_term_agreement = None
        booking.updated_at = now

    Booking.objects.bulk_update(bookings, ["long_term_agreement", "updated_at"])
    for booking in bookings:
        record_booking_audit(
            booking,
            action="lta_unlinked",
            summary=f"Acuerdo LTA desvinculado: {code}",
            changes={
                "source": "lta_agreement",
                "long_term_agreement": {
                    "old": code,
                    "new": None,
                },
            },
            user=user,
        )
        # Recompute LTA-zone / occupancy conflicts after FK clear.
        refresh_related_booking_conflicts(booking, user=user)

    return {
        "unlinked": len(bookings),
        "dry_run": False,
        "agreement_code": code,
    }


def _desired_booking_ids(agreement: LongTermAgreement) -> set[int]:
    """Bookings that should be linked to this agreement under current rules."""
    if not agreement.is_active:
        return set()

    candidates = (
        Booking.objects.filter(
            port_id=agreement.port_id,
            shipping_line_id=agreement.shipping_line_id,
        )
        .filter(
            Q(long_term_agreement__isnull=True)
            | Q(long_term_agreement_id=agreement.pk)
        )
        .exclude(status=BookingStatus.C)
        .select_related("vessel", "position", "shipping_line", "port")
    )

    desired: set[int] = set()
    for booking in candidates:
        if not agreement_covers_booking(agreement, booking):
            continue
        best = find_best_matching_agreement(
            port_id=booking.port_id,
            shipping_line_id=booking.shipping_line_id,
            vessel=booking.vessel,
            call_date=booking.call_date,
            position=booking.position,
        )
        if best is not None and best.pk == agreement.pk:
            desired.add(booking.pk)
    return desired


def link_matching_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
    booking_ids: set[int] | None = None,
) -> dict:
    """
    Assign this LTA to existing bookings that match and have no LTA yet.

    Does not change booking status. Skips cancelled bookings and bookings
    that already have an LTA. Only links when this agreement is the best match.
    """
    if not agreement.is_active:
        return {
            "linked": 0,
            "no_match": 0,
            "dry_run": dry_run,
            "detail": "El acuerdo no está activo.",
            "agreement_code": agreement.code,
        }

    candidates = (
        Booking.objects.filter(
            port_id=agreement.port_id,
            shipping_line_id=agreement.shipping_line_id,
            long_term_agreement__isnull=True,
        )
        .exclude(status=BookingStatus.C)
        .select_related("vessel", "position", "shipping_line", "port")
    )
    if booking_ids is not None:
        candidates = candidates.filter(pk__in=booking_ids)

    to_update: list[Booking] = []
    no_match = 0
    now = timezone.now()

    for booking in candidates:
        if not agreement_covers_booking(agreement, booking):
            no_match += 1
            continue
        best = find_best_matching_agreement(
            port_id=booking.port_id,
            shipping_line_id=booking.shipping_line_id,
            vessel=booking.vessel,
            call_date=booking.call_date,
            position=booking.position,
        )
        if best is None or best.pk != agreement.pk:
            no_match += 1
            continue
        booking.long_term_agreement = agreement
        booking.updated_at = now
        to_update.append(booking)

    if to_update and not dry_run:
        Booking.objects.bulk_update(to_update, ["long_term_agreement", "updated_at"])
        for booking in to_update:
            record_booking_audit(
                booking,
                action="lta_linked",
                summary=f"Acuerdo LTA vinculado: {agreement.code}",
                changes={
                    "source": "lta_agreement",
                    "long_term_agreement": {
                        "old": None,
                        "new": agreement.code,
                    },
                },
                user=user,
            )
            refresh_related_booking_conflicts(booking, user=user)

    return {
        "linked": len(to_update),
        "no_match": no_match,
        "dry_run": dry_run,
        "agreement_code": agreement.code,
    }


def resync_agreement_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
) -> dict:
    """
    Set-diff rematch: unlink = antes − deseado, link = deseado − antes.
    Intersection (keep) is left untouched.
    """
    antes = set(
        Booking.objects.filter(long_term_agreement_id=agreement.pk).values_list(
            "pk",
            flat=True,
        )
    )
    deseado = _desired_booking_ids(agreement)
    to_unlink = antes - deseado
    to_link = deseado - antes

    unlinked = unlink_agreement_bookings(
        agreement,
        user=user,
        dry_run=dry_run,
        booking_ids=to_unlink,
    )
    linked = link_matching_bookings(
        agreement,
        user=user,
        dry_run=dry_run,
        booking_ids=to_link,
    )
    return {
        "unlinked": int(unlinked.get("unlinked") or 0),
        "linked": int(linked.get("linked") or 0),
        "no_match": int(linked.get("no_match") or 0),
        "kept": len(antes & deseado),
        "dry_run": dry_run,
        "agreement_code": agreement.code,
        "detail": linked.get("detail"),
    }
