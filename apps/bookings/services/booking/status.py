from apps.accounts.models import UserRole
from apps.accounts.permissions import user_role
from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.bookings.services.confirmation_pdf import (
    CONFIRMATION_PDF_STATUSES,
    save_confirmation_pdf,
)
from apps.bookings.services.position_assignment import auto_assign_position
from apps.bookings.services.validation import validate_booking_instance


class BookingStatusError(Exception):
    pass


class BookingValidationError(Exception):
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.NR: {BookingStatus.H, BookingStatus.CO, BookingStatus.C},
    BookingStatus.H: {BookingStatus.CO, BookingStatus.C},
    BookingStatus.CO: {BookingStatus.R, BookingStatus.C},
    # Historic LTA track: treat as occupied like CO until closed or cancelled.
    BookingStatus.CL: {BookingStatus.R, BookingStatus.C},
    BookingStatus.LTA: {BookingStatus.CL, BookingStatus.CO, BookingStatus.R, BookingStatus.C},
    BookingStatus.LTD: {BookingStatus.R, BookingStatus.C},
    BookingStatus.R: set(),
    BookingStatus.C: set(),
}


def user_may_authorize_exceptions(user) -> bool:
    """Admin or port_operator may override CL moves and RN-05 red combined LOA."""
    return user_role(user) in {UserRole.ADMIN, UserRole.PORT_OPERATOR}


def update_booking_status(
    booking: Booking,
    new_status: str,
    *,
    user=None,
    cancellation_reason: str | None = None,
    cancellation_evidence=None,
    actual_pax=None,
    eta_real=None,
    etd_real=None,
    acknowledge_combined_red: bool = False,
) -> Booking:
    allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        current = booking.get_status_display()
        target = dict(BookingStatus.choices).get(new_status, new_status)
        raise BookingStatusError(f"No se puede cambiar de «{current}» a «{target}».")

    if new_status == BookingStatus.C:
        reason = cancellation_reason or booking.cancellation_reason
        if not reason:
            raise BookingStatusError("Selecciona el motivo de cancelación.")
        if reason not in CancellationReason.values:
            raise BookingStatusError("Motivo de cancelación no válido.")

    if new_status == BookingStatus.R:
        if actual_pax is not None:
            booking.actual_pax = actual_pax
        if eta_real is not None:
            booking.eta_real = eta_real
        if etd_real is not None:
            booking.etd_real = etd_real
        if booking.actual_pax is None:
            raise BookingStatusError(
                "Indica el PAX real (actual_pax) para cerrar la reserva a Real."
            )

    if new_status == BookingStatus.CO:
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

        if acknowledge_combined_red and not user_may_authorize_exceptions(user):
            raise BookingStatusError(
                "Solo port-operator o admin pueden autorizar la zona roja de LOA combinada."
            )
        ack = bool(acknowledge_combined_red) and user_may_authorize_exceptions(user)

        validation = validate_booking_instance(
            booking,
            acknowledge_combined_red=ack,
        )
        if not validation["valid"]:
            raise BookingValidationError(
                "La reserva no cumple las validaciones operativas.",
                validation["errors"],
            )

    old_status = booking.status
    booking.status = new_status

    update_fields = ["status", "updated_at"]
    if new_status == BookingStatus.C and cancellation_reason:
        booking.cancellation_reason = cancellation_reason
        update_fields.append("cancellation_reason")
    if cancellation_evidence:
        booking.cancellation_evidence = cancellation_evidence
        update_fields.append("cancellation_evidence")
    if new_status == BookingStatus.R:
        if actual_pax is not None:
            update_fields.append("actual_pax")
        if eta_real is not None:
            update_fields.append("eta_real")
        if etd_real is not None:
            update_fields.append("etd_real")

    if new_status in CONFIRMATION_PDF_STATUSES:
        save_confirmation_pdf(booking)
        update_fields.append("confirmation_pdf")

    booking.save(update_fields=list(dict.fromkeys(update_fields)))

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
    eta_real=None,
    etd_real=None,
    planned_pax=None,
    actual_pax=None,
    actual_crew=None,
    port_operator_override: bool = False,
    acknowledge_combined_red: bool = False,
    override_reason: str = "",
) -> Booking:
    changes: dict = {}
    update_fields = ["updated_at"]
    position_changed = False
    schedule_changed = False

    pending_position = position_id is not None and position_id != booking.position_id
    pending_eta = eta is not None and eta != booking.eta
    pending_etd = etd is not None and etd != booking.etd
    cl_schedule_or_berth = pending_position or pending_eta or pending_etd

    if booking.status == BookingStatus.CL and cl_schedule_or_berth:
        if not port_operator_override:
            raise BookingStatusError(
                "Call CL (LTA) es inamovible: un port-operator o admin debe autorizar "
                "el cambio de muelle o ETA/ETD (RN-06)."
            )
        if not user_may_authorize_exceptions(user):
            raise BookingStatusError(
                "Solo port-operator o admin pueden autorizar cambios en un call CL."
            )

    if pending_position:
        changes["position_id"] = {"from": booking.position_id, "to": position_id}
        booking.position_id = position_id or None
        update_fields.append("position")
        position_changed = True

    if pending_eta:
        changes["eta"] = {"from": str(booking.eta) if booking.eta else None, "to": str(eta)}
        booking.eta = eta
        update_fields.append("eta")
        schedule_changed = True

    if pending_etd:
        changes["etd"] = {"from": str(booking.etd) if booking.etd else None, "to": str(etd)}
        booking.etd = etd
        update_fields.append("etd")
        schedule_changed = True

    if eta_real is not None:
        changes["eta_real"] = {
            "from": str(booking.eta_real) if booking.eta_real else None,
            "to": str(eta_real),
        }
        booking.eta_real = eta_real
        update_fields.append("eta_real")

    if etd_real is not None:
        changes["etd_real"] = {
            "from": str(booking.etd_real) if booking.etd_real else None,
            "to": str(etd_real),
        }
        booking.etd_real = etd_real
        update_fields.append("etd_real")

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

    if position_changed or schedule_changed:
        if position_changed:
            if booking.position_id:
                from apps.catalogs.models import Position

                booking.position = Position.objects.select_related("berth", "port").get(
                    pk=booking.position_id,
                )
            else:
                booking.position = None

        if acknowledge_combined_red and not user_may_authorize_exceptions(user):
            raise BookingStatusError(
                "Solo port-operator o admin pueden autorizar la zona roja de LOA combinada."
            )
        ack = bool(acknowledge_combined_red) and user_may_authorize_exceptions(user)

        validation = validate_booking_instance(
            booking,
            acknowledge_combined_red=ack,
        )
        if not validation["valid"]:
            raise BookingValidationError(
                "La reserva no cumple las validaciones operativas.",
                validation["errors"],
            )

    if len(update_fields) > 1:
        booking.save(update_fields=update_fields)
        summary = "Actualización operativa"
        if booking.status == BookingStatus.CL and port_operator_override and cl_schedule_or_berth:
            summary = "Override port-operator en call CL (RN-06)"
            if override_reason:
                changes["override_reason"] = override_reason
        if acknowledge_combined_red:
            changes["acknowledge_combined_red"] = True
        record_booking_audit(
            booking,
            action="operational_update",
            summary=summary,
            changes=changes,
            user=user,
        )

    return booking
