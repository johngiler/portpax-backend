from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.bookings.services.confirmation_pdf import save_confirmation_pdf
from apps.bookings.services.position_assignment import auto_assign_position
from apps.bookings.services.validation import validate_booking_instance


class BookingStatusError(Exception):
    pass


class BookingValidationError(Exception):
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.REQUESTED: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
}


def update_booking_status(
    booking: Booking,
    new_status: str,
    *,
    user=None,
    cancellation_reason: str | None = None,
    cancellation_evidence=None,
) -> Booking:
    allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        current = booking.get_status_display()
        target = dict(BookingStatus.choices).get(new_status, new_status)
        raise BookingStatusError(f"No se puede cambiar de «{current}» a «{target}».")

    if new_status == BookingStatus.CANCELLED:
        reason = cancellation_reason or booking.cancellation_reason
        if not reason:
            raise BookingStatusError("Selecciona el motivo de cancelación.")
        if reason not in CancellationReason.values:
            raise BookingStatusError("Motivo de cancelación no válido.")

    if new_status == BookingStatus.CONFIRMED:
        if not booking.position_id:
            position = auto_assign_position(
                booking.port,
                booking.vessel,
                booking.call_date,
                exclude_booking_id=booking.id,
            )
            if position:
                booking.position = position
                booking.save(update_fields=["position", "updated_at"])

        validation = validate_booking_instance(booking)
        if not booking.position_id:
            raise BookingValidationError(
                "No hay posición disponible que cumpla las dimensiones del barco.",
                [{"level": "error", "code": "no_position", "message": "Sin posición asignada."}],
            )
        if not validation["valid"]:
            raise BookingValidationError(
                "La reserva no cumple las validaciones operativas.",
                validation["errors"],
            )

    old_status = booking.status
    booking.status = new_status

    update_fields = ["status", "updated_at"]
    if new_status == BookingStatus.CANCELLED and cancellation_reason:
        booking.cancellation_reason = cancellation_reason
        update_fields.append("cancellation_reason")
    if cancellation_evidence:
        booking.cancellation_evidence = cancellation_evidence
        update_fields.append("cancellation_evidence")

    if new_status == BookingStatus.CONFIRMED:
        save_confirmation_pdf(booking)
        update_fields.append("confirmation_pdf")

    booking.save(update_fields=update_fields)

    record_booking_audit(
        booking,
        action="status_change",
        summary=f"Estado: {dict(BookingStatus.choices).get(new_status, new_status)}",
        changes={"status": {"from": old_status, "to": new_status}},
        user=user,
    )

    return booking


def update_booking_operational(
    booking: Booking,
    *,
    user=None,
    position_id=None,
    eta=None,
    etd=None,
    planned_pax=None,
    actual_pax=None,
    actual_crew=None,
) -> Booking:
    changes: dict = {}
    update_fields = ["updated_at"]

    if position_id is not None and position_id != booking.position_id:
        changes["position_id"] = {"from": booking.position_id, "to": position_id}
        booking.position_id = position_id or None
        update_fields.append("position")

    if eta is not None:
        changes["eta"] = {"from": str(booking.eta) if booking.eta else None, "to": str(eta)}
        booking.eta = eta
        update_fields.append("eta")

    if etd is not None:
        changes["etd"] = {"from": str(booking.etd) if booking.etd else None, "to": str(etd)}
        booking.etd = etd
        update_fields.append("etd")

    if planned_pax is not None:
        changes["planned_pax"] = {"from": booking.planned_pax, "to": planned_pax}
        booking.planned_pax = planned_pax
        update_fields.append("planned_pax")

    if actual_pax is not None:
        changes["actual_pax"] = {"from": booking.actual_pax, "to": actual_pax}
        booking.actual_pax = actual_pax
        update_fields.append("actual_pax")

    if actual_crew is not None:
        changes["actual_crew"] = {"from": booking.actual_crew, "to": actual_crew}
        booking.actual_crew = actual_crew
        update_fields.append("actual_crew")

    if len(update_fields) > 1:
        booking.save(update_fields=update_fields)
        record_booking_audit(
            booking,
            action="operational_update",
            summary="Actualización operativa",
            changes=changes,
            user=user,
        )

    return booking
