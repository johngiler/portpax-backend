from apps.accounts.models import UserRole
from apps.accounts.permissions import user_role
from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.bookings.services.confirmation_pdf import (
    CONFIRMATION_PDF_STATUSES,
    save_confirmation_pdf,
)
from apps.bookings.services.position_assignment import auto_assign_position


class BookingStatusError(Exception):
    pass


class BookingValidationError(Exception):
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.NR: {BookingStatus.H, BookingStatus.CO, BookingStatus.LTA, BookingStatus.C},
    BookingStatus.H: {BookingStatus.CO, BookingStatus.C},
    BookingStatus.CO: {BookingStatus.R, BookingStatus.C},
    # Historic LTA track: treat as occupied like CO until closed or cancelled.
    BookingStatus.CL: {BookingStatus.R, BookingStatus.C},
    BookingStatus.LTA: {BookingStatus.CL, BookingStatus.CO, BookingStatus.R, BookingStatus.C},
    BookingStatus.LTD: {BookingStatus.R, BookingStatus.C},
    BookingStatus.R: set(),
    BookingStatus.C: {BookingStatus.H},
}


def user_may_authorize_exceptions(user) -> bool:
    """Admin or port_operator may override CL moves and RN-05 red combined LOA."""
    return user_role(user) in {UserRole.ADMIN, UserRole.PORT_OPERATOR}


def update_booking_status(
    booking: Booking,
    new_status: str,
    *,
    user=None,
    request=None,
    cancellation_reason: str | None = None,
    cancellation_evidence=None,
    actual_pax=None,
    eta_real=None,
    etd_real=None,
    acknowledge_combined_red: bool = False,
    require_lta_agreement: bool = True,
    audit_source: str | None = None,
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

        # Operational conflicts are non-blocking; persist on save below.
        _ = ack

    if new_status in (BookingStatus.LTA, BookingStatus.CL):
        from apps.bookings.services.lta.matching import find_best_matching_agreement

        agreement = booking.long_term_agreement
        if agreement is None:
            agreement = find_best_matching_agreement(
                port_id=booking.port_id,
                shipping_line_id=booking.shipping_line_id,
                vessel=booking.vessel,
                call_date=booking.call_date,
                position=booking.position,
            )
        if agreement is None and require_lta_agreement:
            raise BookingStatusError(
                "No hay un acuerdo LTA vigente que cubra esta reserva "
                "(puerto, naviera, barco, día y posición)."
            )
        if agreement is not None:
            booking.long_term_agreement = agreement

    old_status = booking.status
    cleared_lta_code: str | None = None
    booking.status = new_status

    update_fields = ["status", "updated_at"]
    if new_status in (BookingStatus.LTA, BookingStatus.CL) and booking.long_term_agreement_id:
        update_fields.append("long_term_agreement")
    reactivation_clears: dict = {}
    if new_status == BookingStatus.H and old_status == BookingStatus.C:
        if booking.cancellation_reason:
            reactivation_clears["cancellation_reason"] = {
                "from": booking.cancellation_reason,
                "to": None,
            }
            booking.cancellation_reason = ""
            update_fields.append("cancellation_reason")
        if booking.cancellation_evidence:
            reactivation_clears["cancellation_evidence"] = {"from": "file", "to": None}
            booking.cancellation_evidence.delete(save=False)
            booking.cancellation_evidence = None
            update_fields.append("cancellation_evidence")

    if new_status == BookingStatus.C:
        if booking.long_term_agreement_id:
            old_lta = getattr(booking, "long_term_agreement", None)
            cleared_lta_code = (
                getattr(old_lta, "code", None) or str(booking.long_term_agreement_id)
            )
            booking.long_term_agreement = None
            update_fields.append("long_term_agreement")
        if cancellation_reason:
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

    from apps.bookings.services.validation.conflicts import (
        refresh_related_booking_conflicts,
    )

    refresh_related_booking_conflicts(booking, user=user, request=request)

    status_changes: dict = {"status": {"from": old_status, "to": new_status}}
    status_changes.update(reactivation_clears)
    if cleared_lta_code is not None:
        status_changes["long_term_agreement"] = {
            "from": cleared_lta_code,
            "to": None,
        }
    if audit_source:
        status_changes["source"] = audit_source
    record_booking_audit(
        booking,
        action="status_change",
        summary=f"Estado: {dict(BookingStatus.choices).get(new_status, new_status)}",
        changes=status_changes,
        user=user,
        request=request,
    )

    return booking


def update_booking_operational(
    booking: Booking,
    *,
    user=None,
    request=None,
    position_id=None,
    eta=None,
    etd=None,
    eta_real=None,
    etd_real=None,
    planned_pax=None,
    actual_pax=None,
    actual_crew=None,
    operation_notes=None,
    arrival_manifest=None,
    port_operator_override: bool = False,
    acknowledge_combined_red: bool = False,
    override_reason: str = "",
    audit_source: str | None = None,
) -> Booking:
    from apps.accounts.permissions import (
        user_may_edit_booking_schedule,
        user_may_edit_port_operations,
    )

    changes: dict = {}
    update_fields = ["updated_at"]
    position_changed = False
    schedule_changed = False

    pending_position = position_id is not None and position_id != booking.position_id
    pending_eta = eta is not None and eta != booking.eta
    pending_etd = etd is not None and etd != booking.etd
    pending_schedule = pending_position or pending_eta or pending_etd

    pending_port_ops = any(
        (
            eta_real is not None,
            etd_real is not None,
            actual_pax is not None,
            actual_crew is not None,
            operation_notes is not None,
            arrival_manifest is not None,
        )
    )

    if pending_schedule and not user_may_edit_booking_schedule(user):
        raise BookingStatusError(
            "No tienes permiso para cambiar posición u horarios planificados."
        )
    if pending_port_ops and not user_may_edit_port_operations(user):
        raise BookingStatusError(
            "No tienes permiso para editar datos de arribo (PAX real, tripulación, "
            "manifiesto, ETA/ETD real o notas de operación)."
        )
    # Planned PAX is a create-time snapshot; ignore client updates.
    _ = planned_pax
    _ = override_reason
    _ = port_operator_override

    if pending_position:
        old_position_id = booking.position_id
        old_position_code = None
        if booking.position_id:
            old_pos = getattr(booking, "position", None)
            if old_pos is not None:
                old_position_code = getattr(old_pos, "code", None)
        changes["position_id"] = {
            "from": old_position_id,
            "to": position_id,
            "from_code": old_position_code,
            "to_code": None,
        }
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

    if actual_pax is not None:
        changes["actual_pax"] = {"from": booking.actual_pax, "to": actual_pax}
        booking.actual_pax = actual_pax
        update_fields.append("actual_pax")

    if actual_crew is not None:
        changes["actual_crew"] = {"from": booking.actual_crew, "to": actual_crew}
        booking.actual_crew = actual_crew
        update_fields.append("actual_crew")

    if operation_notes is not None and operation_notes != booking.operation_notes:
        changes["operation_notes"] = {
            "from": booking.operation_notes,
            "to": operation_notes,
        }
        booking.operation_notes = operation_notes
        update_fields.append("operation_notes")

    if arrival_manifest is not None:
        changes["arrival_manifest"] = {
            "from": "file" if booking.arrival_manifest else None,
            "to": "file",
        }
        booking.arrival_manifest = arrival_manifest
        update_fields.append("arrival_manifest")

    if position_changed or schedule_changed:
        if position_changed:
            if booking.position_id:
                from apps.catalogs.models import Position

                booking.position = Position.objects.select_related("berth", "port").get(
                    pk=booking.position_id,
                )
            else:
                booking.position = None
            if "position_id" in changes and isinstance(changes["position_id"], dict):
                changes["position_id"]["to_code"] = (
                    booking.position.code if booking.position is not None else None
                )

        if acknowledge_combined_red and not user_may_authorize_exceptions(user):
            raise BookingStatusError(
                "Solo port-operator o admin pueden autorizar la zona roja de LOA combinada."
            )
        ack = bool(acknowledge_combined_red) and user_may_authorize_exceptions(user)
        # Operational conflicts are non-blocking; refreshed after save.
        _ = ack

        if position_changed:
            from apps.bookings.services.lta.matching import find_best_matching_agreement

            old_lta_id = booking.long_term_agreement_id
            old_lta = getattr(booking, "long_term_agreement", None)
            old_code = getattr(old_lta, "code", None) if old_lta is not None else None
            new_agreement = find_best_matching_agreement(
                port_id=booking.port_id,
                shipping_line_id=booking.shipping_line_id,
                vessel=booking.vessel,
                call_date=booking.call_date,
                position=booking.position,
            )
            new_lta_id = new_agreement.id if new_agreement is not None else None
            if new_lta_id != old_lta_id:
                changes["long_term_agreement_id"] = {
                    "from": old_lta_id,
                    "to": new_lta_id,
                    "from_code": old_code,
                    "to_code": new_agreement.code if new_agreement is not None else None,
                }
                booking.long_term_agreement = new_agreement
                update_fields.append("long_term_agreement")

    if len(update_fields) > 1:
        booking.save(update_fields=update_fields)
        summary = "Actualización operativa"
        if position_changed and not schedule_changed:
            summary = "Reasignación de posición"
        elif schedule_changed and not position_changed:
            summary = "Cambio de horario"
        if acknowledge_combined_red:
            changes["acknowledge_combined_red"] = True
        if audit_source:
            changes["source"] = audit_source
        record_booking_audit(
            booking,
            action="operational_update",
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
