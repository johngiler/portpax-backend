"""Update booking identity fields (port / line / vessel / date / notes)."""

from __future__ import annotations

from datetime import date

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.booking.status import BookingValidationError
from apps.bookings.services.booking.shipping_line_group import (
    UPDATE_GROUP_MISMATCH_MESSAGE as GROUP_MISMATCH_MESSAGE,
    group_mismatch_error,
    rematch_vessel_by_name,
    same_shipping_line_group,
    vessel_line_mismatch_error,
)
from apps.catalogs.models import Port, ShippingLine, Vessel

__all__ = ["GROUP_MISMATCH_MESSAGE", "update_booking_identity"]


def _not_found(entity: str) -> BookingValidationError:
    return BookingValidationError(
        f"{entity} no encontrado.",
        [
            {
                "code": "not_found",
                "message": f"{entity} no encontrado.",
                "severity": "error",
            }
        ],
    )


def update_booking_identity(
    booking: Booking,
    *,
    user=None,
    request=None,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    call_date: date | None = None,
    notes: str | None = None,
) -> Booking:
    if booking.status == BookingStatus.C:
        raise BookingValidationError(
            "No se puede editar una reserva cancelada.",
            [
                {
                    "code": "booking_cancelled",
                    "message": "No se puede editar una reserva cancelada.",
                    "severity": "error",
                }
            ],
        )

    changes: dict = {}
    update_fields: list[str] = ["updated_at"]

    old_port = booking.port
    old_line = booking.shipping_line
    old_vessel = booking.vessel
    old_call_date = booking.call_date
    old_code = booking.booking_code
    old_lta_id = booking.long_term_agreement_id
    old_notes = booking.notes

    new_port = old_port
    if port_id is not None and port_id != booking.port_id:
        try:
            new_port = Port.objects.get(pk=port_id)
        except Port.DoesNotExist as exc:
            raise _not_found("Puerto") from exc
        changes["port_id"] = {
            "from": booking.port_id,
            "to": new_port.id,
            "from_code": old_port.code,
            "to_code": new_port.code,
            "from_name": old_port.name,
            "to_name": new_port.name,
        }
        booking.port = new_port
        update_fields.append("port")

    new_line = old_line
    if shipping_line_id is not None and shipping_line_id != booking.shipping_line_id:
        try:
            new_line = ShippingLine.objects.select_related("group").get(pk=shipping_line_id)
        except ShippingLine.DoesNotExist as exc:
            raise _not_found("Naviera") from exc
        if new_line.group_id != old_line.group_id:
            raise group_mismatch_error(for_update=True)
        changes["shipping_line_id"] = {
            "from": booking.shipping_line_id,
            "to": new_line.id,
            "from_code": old_line.code,
            "to_code": new_line.code,
            "from_name": old_line.name,
            "to_name": new_line.name,
        }
        booking.shipping_line = new_line
        update_fields.append("shipping_line")

    new_vessel = old_vessel
    if vessel_id is not None and vessel_id != booking.vessel_id:
        try:
            new_vessel = (
                Vessel.objects.select_related("shipping_line", "shipping_line__group")
                .get(pk=vessel_id)
            )
        except Vessel.DoesNotExist as exc:
            raise _not_found("Barco") from exc
        if not same_shipping_line_group(new_line, new_vessel):
            raise group_mismatch_error(for_update=True)
        if new_vessel.shipping_line_id != new_line.id:
            rematch = rematch_vessel_by_name(
                new_vessel.name,
                shipping_line_id=new_line.id,
                shipping_line_group_id=new_line.group_id,
            )
            if rematch:
                new_vessel = rematch
            else:
                raise vessel_line_mismatch_error()
        if new_vessel.id != old_vessel.id:
            changes["vessel_id"] = {
                "from": booking.vessel_id,
                "to": new_vessel.id,
                "from_name": old_vessel.name,
                "to_name": new_vessel.name,
            }
            booking.vessel = new_vessel
            update_fields.append("vessel")
    elif new_vessel.shipping_line_id != new_line.id:
        rematch = rematch_vessel_by_name(
            new_vessel.name,
            shipping_line_id=new_line.id,
            shipping_line_group_id=new_line.group_id,
        )
        if rematch:
            new_vessel = rematch
            changes["vessel_id"] = {
                "from": booking.vessel_id,
                "to": new_vessel.id,
                "from_name": old_vessel.name,
                "to_name": new_vessel.name,
            }
            booking.vessel = new_vessel
            update_fields.append("vessel")
        else:
            raise vessel_line_mismatch_error(
                "El barco actual no pertenece a la naviera seleccionada. "
                "Elige otro barco."
            )

    new_call_date = old_call_date
    if call_date is not None and call_date != booking.call_date:
        changes["call_date"] = {
            "from": old_call_date.isoformat(),
            "to": call_date.isoformat(),
        }
        booking.call_date = call_date
        new_call_date = call_date
        update_fields.append("call_date")

    if notes is not None and notes != old_notes:
        changes["notes"] = {"from": old_notes or None, "to": notes or None}
        booking.notes = notes
        update_fields.append("notes")

    identity_keys = {"port", "shipping_line", "vessel", "call_date"}
    identity_changed = bool(identity_keys.intersection(update_fields))

    if not identity_changed and "notes" not in update_fields:
        return booking

    if identity_changed:
        clash = (
            Booking.objects.filter(
                port_id=new_port.id,
                vessel_id=new_vessel.id,
                call_date=new_call_date,
            )
            .exclude(pk=booking.pk)
            .first()
        )
        if clash is not None:
            raise BookingValidationError(
                f"Ya existe una reserva para ese puerto, barco y fecha "
                f"({clash.booking_code}).",
                [
                    {
                        "code": "duplicate_port_vessel_date",
                        "message": (
                            f"Ya existe una reserva para ese puerto, barco y fecha "
                            f"({clash.booking_code})."
                        ),
                        "severity": "error",
                    }
                ],
            )

        existing_codes = set(Booking.objects.values_list("booking_code", flat=True))
        existing_codes.discard(old_code)
        new_code = resolve_unique_booking_code(
            new_port,
            new_line,
            new_vessel,
            new_call_date,
            existing_codes,
        )
        if new_code != old_code:
            changes["booking_code"] = {"from": old_code, "to": new_code}
            booking.booking_code = new_code
            update_fields.append("booking_code")

        # Position belongs to the old port — clear when port changes.
        position = booking.position
        if position is not None and position.port_id != new_port.id:
            changes["position_id"] = {
                "from": booking.position_id,
                "to": None,
                "from_code": position.code,
                "to_code": None,
            }
            booking.position = None
            update_fields.append("position")

        if old_lta_id is not None:
            changes["long_term_agreement_id"] = {"from": old_lta_id, "to": None}
            booking.long_term_agreement = None
            update_fields.append("long_term_agreement")

    booking.save(update_fields=list(dict.fromkeys(update_fields)))

    summary = "Actualización de escala"
    if "booking_code" in changes:
        summary = f"Nomenclatura: {old_code} → {booking.booking_code}"
    elif identity_changed:
        summary = "Actualización de identidad de escala"
    elif "notes" in changes:
        summary = "Actualización de notas"

    record_booking_audit(
        booking,
        action="identity_update",
        summary=summary,
        changes=changes,
        user=user,
        request=request,
    )

    from apps.bookings.services.validation.conflicts import (
        refresh_related_booking_conflicts,
    )

    refresh_related_booking_conflicts(booking, user=user, request=request)
    return booking
