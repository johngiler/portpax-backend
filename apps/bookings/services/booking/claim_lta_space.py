"""Claim a reserved LTA booking in place (LTA → CL). Shared by mass create and edit."""

from __future__ import annotations

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.identity import update_booking_identity
from apps.bookings.services.booking.status import (
    BookingStatusError,
    BookingValidationError,
    update_booking_operational,
    update_booking_status,
)
from apps.catalogs.models import ShippingLine, Vessel


class ClaimLtaSpaceError(Exception):
    def __init__(self, message: str, field: str = "claim_lta_space"):
        super().__init__(message)
        self.field = field


def claim_lta_space_booking(
    *,
    candidate_id: int,
    vessel_id: int,
    shipping_line_id: int,
    eta,
    etd,
    preferred_position_id: int | None,
    user=None,
    request=None,
    audit_source: str = "mass_import",
    audit_extra: dict | None = None,
):
    """
    Claim reserved LTA capacity in place: update vessel/line (via identity,
    regenerating booking_code), ETA/ETD/position, then LTA → CL.
    """
    extra = dict(audit_extra or {})
    extra["claimed_lta_space"] = True

    booking = (
        Booking.objects.select_related(
            "vessel",
            "position",
            "port",
            "shipping_line",
            "shipping_line__group",
            "long_term_agreement",
        )
        .filter(pk=candidate_id, status=BookingStatus.LTA)
        .first()
    )
    if booking is None:
        raise ClaimLtaSpaceError("El espacio LTA a reclamar ya no está disponible.")

    claim_line = (
        ShippingLine.objects.select_related("group")
        .filter(pk=shipping_line_id, is_active=True)
        .first()
    )
    if claim_line is None:
        raise ClaimLtaSpaceError("Naviera no válida.", "shipping_line_id")

    vessel = (
        Vessel.objects.filter(pk=vessel_id, is_active=True)
        .select_related("shipping_line", "shipping_line__group")
        .first()
    )
    if vessel is None:
        raise ClaimLtaSpaceError("Barco no válido.", "vessel_id")
    if vessel.shipping_line_id != shipping_line_id:
        raise ClaimLtaSpaceError(
            "El barco no pertenece a la naviera de la fila.",
            "vessel_id",
        )
    booking_group = (
        booking.shipping_line.group_id if booking.shipping_line_id else None
    )
    if booking_group is None or booking_group != claim_line.group_id:
        raise ClaimLtaSpaceError("El espacio LTA pertenece a otro grupo de naviera.")

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
        raise ClaimLtaSpaceError(
            "Ya existe una reserva para este barco/puerto/fecha; "
            "no se puede reclamar el LTA con ese barco.",
            "vessel_id",
        )

    position_id = preferred_position_id
    if position_id is None:
        position_id = booking.position_id

    try:
        # Keep existing LTA FK: claimant vessel may not be on the agreement list.
        booking = update_booking_identity(
            booking,
            user=user,
            request=request,
            shipping_line_id=shipping_line_id,
            vessel_id=vessel_id,
            audit_source=audit_source,
            audit_extra=extra,
            rematch_lta=False,
        )
        booking.refresh_from_db()
        update_booking_operational(
            booking,
            user=user,
            request=request,
            position_id=position_id,
            eta=eta,
            etd=etd,
            audit_source=audit_source,
            audit_extra=extra,
        )
        booking.refresh_from_db()
        update_booking_status(
            booking,
            BookingStatus.CL,
            user=user,
            request=request,
            require_lta_agreement=False,
            audit_source=audit_source,
            audit_extra=extra,
        )
    except BookingStatusError as exc:
        raise ClaimLtaSpaceError(str(exc)) from exc
    except BookingValidationError as exc:
        msgs = [
            (e.get("message") if isinstance(e, dict) else str(e))
            for e in (exc.errors or [])
        ]
        detail = "; ".join(m for m in msgs if m) or str(exc)
        raise ClaimLtaSpaceError(detail) from exc

    booking.refresh_from_db()
    record_booking_audit(
        booking,
        action="operational_update",
        summary="Espacio LTA reclamado (Confirmada LTA)",
        changes={"claimed_lta_space": True, "status": {"from": "lta", "to": "cl"}},
        user=user,
        request=request,
    )
    return booking
