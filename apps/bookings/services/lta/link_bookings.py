"""Link / unlink bookings to a LongTermAgreement by matching rules."""

from __future__ import annotations

from django.utils import timezone

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, LongTermAgreement
from apps.bookings.services.lta.matching import (
    agreement_covers_cadence,
    agreement_covers_position,
    agreement_covers_validity,
    agreement_covers_vessel,
    agreement_covers_weekday,
    find_best_matching_agreement,
)


def agreement_covers_booking(agreement: LongTermAgreement, booking: Booking) -> bool:
    if not agreement_covers_validity(agreement, booking.call_date):
        return False
    if not agreement_covers_weekday(agreement, booking.call_date):
        return False
    if not agreement_covers_cadence(agreement, booking.call_date):
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
) -> dict:
    """Clear long_term_agreement FK on all bookings linked to this agreement."""
    qs = Booking.objects.filter(long_term_agreement_id=agreement.pk).select_related(
        "vessel",
        "position",
        "shipping_line",
        "port",
    )
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
                "long_term_agreement": {
                    "old": code,
                    "new": None,
                }
            },
            user=user,
        )

    return {
        "unlinked": len(bookings),
        "dry_run": False,
        "agreement_code": code,
    }


def link_matching_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
) -> dict:
    """
    Assign this LTA to existing bookings that match and have no LTA yet.

    Does not change booking status. Skips cancelled bookings and bookings
    that already have an LTA. Only links when this agreement is the best match.
    """
    if not agreement.is_active:
        return {
            "linked": 0,
            "skipped": 0,
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

    to_update: list[Booking] = []
    skipped = 0
    now = timezone.now()

    for booking in candidates:
        if not agreement_covers_booking(agreement, booking):
            skipped += 1
            continue
        best = find_best_matching_agreement(
            port_id=booking.port_id,
            shipping_line_id=booking.shipping_line_id,
            vessel=booking.vessel,
            call_date=booking.call_date,
            position=booking.position,
        )
        if best is None or best.pk != agreement.pk:
            skipped += 1
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
                    "long_term_agreement": {
                        "old": None,
                        "new": agreement.code,
                    }
                },
                user=user,
            )

    return {
        "linked": len(to_update),
        "skipped": skipped,
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
    Unlink all bookings on this agreement, then re-link matches under current rules.
    """
    unlinked = unlink_agreement_bookings(agreement, user=user, dry_run=dry_run)
    linked = link_matching_bookings(agreement, user=user, dry_run=dry_run)
    return {
        "unlinked": int(unlinked.get("unlinked") or 0),
        "linked": int(linked.get("linked") or 0),
        "skipped": int(linked.get("skipped") or 0),
        "dry_run": dry_run,
        "agreement_code": agreement.code,
        "detail": linked.get("detail"),
    }
