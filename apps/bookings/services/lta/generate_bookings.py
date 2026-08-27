"""Materialize LTA ghost bookings (Fase C — Generar / Regenerar)."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, LongTermAgreement
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.lta.generate_dates import iter_agreement_candidate_dates
from apps.bookings.services.lta.link_bookings import resync_agreement_bookings
from apps.bookings.services.validation.conflicts import (
    refresh_related_booking_conflicts,
)
from apps.catalogs.models import Position, Vessel


class LtaGenerateError(Exception):
    """Business rule blocking Generar/Regenerar (sync validation)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_generate_prerequisites(agreement: LongTermAgreement) -> None:
    """Raise LtaGenerateError if the agreement cannot materialize bookings."""
    if not agreement.is_active:
        raise LtaGenerateError("El acuerdo no está activo.")
    if agreement.all_vessels:
        raise LtaGenerateError(
            "Indica barcos explícitos en el acuerdo (no «todos los barcos») "
            "para poder generar reservas."
        )
    vessels = list(agreement.vessels.all().order_by("name", "id"))
    if not vessels:
        raise LtaGenerateError(
            "El acuerdo no tiene barcos. Agrega al menos un barco para generar."
        )
    positions = list(agreement.positions.all().order_by("code", "id"))
    if not positions:
        raise LtaGenerateError(
            "El acuerdo no tiene posiciones. Agrega al menos una posición (P1, P2…)."
        )


def _first_vessel(agreement: LongTermAgreement) -> Vessel:
    vessels = list(agreement.vessels.all().order_by("name", "id"))
    return vessels[0]


def _positions(agreement: LongTermAgreement) -> list[Position]:
    return list(agreement.positions.select_related("port").order_by("code", "id"))


def _slot_exists(
    *,
    port_id: int,
    vessel_id: int,
    position_id: int,
    call_date: date,
) -> bool:
    return (
        Booking.objects.filter(
            port_id=port_id,
            vessel_id=vessel_id,
            position_id=position_id,
            call_date=call_date,
        )
        .exclude(status=BookingStatus.C)
        .exists()
    )


def mark_bookings_generated(agreement: LongTermAgreement) -> None:
    """Flip the first-generation flag (idempotent)."""
    if agreement.bookings_generated:
        return
    LongTermAgreement.objects.filter(pk=agreement.pk).update(bookings_generated=True)
    agreement.bookings_generated = True


def materialize_agreement_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
    today: date | None = None,
) -> dict:
    """
    Create missing Booking rows: first explicit vessel × each position × each A1 date.

    Status = LTA. Skips slots that already have a non-cancelled booking.
    """
    validate_generate_prerequisites(agreement)
    today = today or date.today()
    vessel = _first_vessel(agreement)
    positions = _positions(agreement)
    dates = iter_agreement_candidate_dates(agreement, today)

    planned = []
    for call_date in dates:
        for position in positions:
            planned.append((call_date, position))

    to_create: list[tuple[date, Position]] = []
    skipped = 0
    for call_date, position in planned:
        if _slot_exists(
            port_id=agreement.port_id,
            vessel_id=vessel.pk,
            position_id=position.pk,
            call_date=call_date,
        ):
            skipped += 1
            continue
        to_create.append((call_date, position))

    if dry_run:
        return {
            "created": len(to_create),
            "skipped": skipped,
            "candidates": len(planned),
            "dates": len(dates),
            "vessel_id": vessel.pk,
            "vessel_name": vessel.name,
            "dry_run": True,
            "agreement_code": agreement.code,
            "bookings_generated": agreement.bookings_generated,
        }

    port = agreement.port
    shipping_line = agreement.shipping_line
    existing_codes = set(
        Booking.objects.filter(booking_code__startswith=port.code.upper()).values_list(
            "booking_code",
            flat=True,
        )
    )
    created_rows: list[Booking] = []

    with transaction.atomic():
        for call_date, position in to_create:
            code = resolve_unique_booking_code(
                port,
                shipping_line,
                vessel,
                call_date,
                existing_codes,
            )
            existing_codes.add(code)
            booking = Booking(
                port=port,
                shipping_line=shipping_line,
                vessel=vessel,
                position=position,
                call_date=call_date,
                booking_code=code,
                status=BookingStatus.LTA,
                planned_pax=agreement.min_packs,
                notes=f"Generada desde LTA {agreement.code}",
                created_by=user if getattr(user, "is_authenticated", False) else None,
                long_term_agreement=agreement,
            )
            created_rows.append(booking)
        if created_rows:
            Booking.objects.bulk_create(created_rows)

    # Re-load for audits / conflict refresh (bulk_create may omit PKs on some DBs).
    if created_rows:
        codes = [b.booking_code for b in created_rows]
        created = list(
            Booking.objects.filter(booking_code__in=codes).select_related(
                "port",
                "shipping_line",
                "vessel",
                "position",
                "long_term_agreement",
            )
        )
    else:
        created = []

    for booking in created:
        refresh_related_booking_conflicts(booking, user=user)
        record_booking_audit(
            booking,
            action="created",
            summary=f"Reserva generada desde LTA ({agreement.code})",
            changes={
                "source": "lta_generate",
                "long_term_agreement": {"old": None, "new": agreement.code},
                "status": {"from": None, "to": BookingStatus.LTA},
            },
            user=user,
        )

    mark_bookings_generated(agreement)

    return {
        "created": len(created),
        "skipped": skipped,
        "candidates": len(planned),
        "dates": len(dates),
        "vessel_id": vessel.pk,
        "vessel_name": vessel.name,
        "dry_run": False,
        "agreement_code": agreement.code,
        "bookings_generated": True,
    }


def regenerate_agreement_bookings(
    agreement: LongTermAgreement,
    *,
    user=None,
    dry_run: bool = False,
    today: date | None = None,
) -> dict:
    """Set-diff resync of existing links, then materialize missing A1 slots."""
    validate_generate_prerequisites(agreement)
    resync = resync_agreement_bookings(agreement, user=user, dry_run=dry_run)
    materialize = materialize_agreement_bookings(
        agreement,
        user=user,
        dry_run=dry_run,
        today=today,
    )
    return {
        "unlinked": int(resync.get("unlinked") or 0),
        "linked": int(resync.get("linked") or 0),
        "kept": int(resync.get("kept") or 0),
        "created": int(materialize.get("created") or 0),
        "skipped": int(materialize.get("skipped") or 0),
        "candidates": int(materialize.get("candidates") or 0),
        "dates": int(materialize.get("dates") or 0),
        "vessel_name": materialize.get("vessel_name"),
        "dry_run": dry_run,
        "agreement_code": agreement.code,
        "bookings_generated": True if not dry_run else agreement.bookings_generated,
    }
