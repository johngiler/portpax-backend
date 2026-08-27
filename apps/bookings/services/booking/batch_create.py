"""Create multiple bookings for the same port / line / vessel."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from django.db import transaction

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.position_assignment import resolve_booking_position
from apps.bookings.services.validation.rules import related_position_ids
from apps.bookings.services.booking.shipping_line_group import (
    CREATE_GROUP_MISMATCH_MESSAGE,
)
from apps.catalogs.models import Port, ShippingLine, Vessel

# Mass-import initial statuses (NR retired from this flow; C/R not created here).
BULK_CREATE_STATUSES = frozenset(
    {
        BookingStatus.H,
        BookingStatus.CO,
        BookingStatus.CL,
        BookingStatus.LTA,
        BookingStatus.LTD,
    }
)


class BookingBatchCreateError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def _normalize_entries(
    *,
    call_dates: list[date] | None,
    entries: list[dict[str, Any]] | None,
    default_eta: time | None,
    default_etd: time | None,
    default_planned_pax: int | None,
    default_position_id: int | None,
    default_status: str,
) -> list[dict[str, Any]]:
    """Build one spec per call date (entries win over shared defaults)."""
    if entries:
        by_date: dict[date, dict[str, Any]] = {}
        for raw in entries:
            call_date = raw["call_date"]
            if call_date in by_date:
                raise BookingBatchCreateError("Las fechas deben ser únicas.", "entries")
            status = raw.get("status") or default_status
            if status not in BULK_CREATE_STATUSES:
                raise BookingBatchCreateError("Estado inicial no válido.", "status")
            by_date[call_date] = {
                "call_date": call_date,
                "eta": raw.get("eta", default_eta),
                "etd": raw.get("etd", default_etd),
                "planned_pax": raw.get("planned_pax", default_planned_pax),
                "position_id": raw.get("position", default_position_id),
                "status": status,
            }
        return [by_date[d] for d in sorted(by_date)]

    if not call_dates:
        raise BookingBatchCreateError(
            "Selecciona al menos una fecha.",
            "call_dates",
        )
    if default_status not in BULK_CREATE_STATUSES:
        raise BookingBatchCreateError("Estado inicial no válido.", "status")
    unique_dates = sorted({d for d in call_dates})
    if len(unique_dates) != len(call_dates):
        raise BookingBatchCreateError("Las fechas deben ser únicas.", "call_dates")
    return [
        {
            "call_date": call_date,
            "eta": default_eta,
            "etd": default_etd,
            "planned_pax": default_planned_pax,
            "position_id": default_position_id,
            "status": default_status,
        }
        for call_date in unique_dates
    ]


def create_booking_batch(
    *,
    port_id: int,
    shipping_line_id: int,
    vessel_id: int,
    call_dates: list[date] | None = None,
    entries: list[dict[str, Any]] | None = None,
    notes: str = "",
    created_by=None,
    eta=None,
    etd=None,
    planned_pax: int | None = None,
    preferred_position_id: int | None = None,
    audit_changes: dict | None = None,
    status: str = BookingStatus.H,
) -> list[Booking]:
    specs = _normalize_entries(
        call_dates=call_dates,
        entries=entries,
        default_eta=eta,
        default_etd=etd,
        default_planned_pax=planned_pax,
        default_position_id=preferred_position_id,
        default_status=status,
    )
    unique_dates = [spec["call_date"] for spec in specs]

    try:
        port = Port.objects.get(pk=port_id, is_active=True)
    except Port.DoesNotExist:
        raise BookingBatchCreateError("Puerto no válido.", "port")

    try:
        shipping_line = ShippingLine.objects.select_related("group").get(
            pk=shipping_line_id, is_active=True
        )
    except ShippingLine.DoesNotExist:
        raise BookingBatchCreateError("Naviera no válida.", "shipping_line")

    try:
        vessel = Vessel.objects.select_related(
            "shipping_line",
            "shipping_line__group",
        ).get(
            pk=vessel_id,
            is_active=True,
        )
    except Vessel.DoesNotExist:
        raise BookingBatchCreateError("Barco no válido.", "vessel")

    if vessel.shipping_line.group_id != shipping_line.group_id:
        raise BookingBatchCreateError(
            CREATE_GROUP_MISMATCH_MESSAGE,
            "vessel",
        )
    if vessel.shipping_line_id != shipping_line.id:
        raise BookingBatchCreateError(
            "El barco no pertenece a la naviera seleccionada.",
            "vessel",
        )

    conflicts = Booking.objects.filter(
        port=port,
        vessel=vessel,
        call_date__in=unique_dates,
    ).values_list("call_date", flat=True)
    if conflicts:
        conflict_str = ", ".join(d.isoformat() for d in conflicts)
        raise BookingBatchCreateError(
            f"Ya existen reservas para estas fechas: {conflict_str}.",
            "call_dates",
        )

    from apps.bookings.services.lta.matching import find_best_matching_agreement
    from apps.bookings.services.validation.conflicts import (
        refresh_related_booking_conflicts,
    )

    for spec in specs:
        if spec["status"] not in {BookingStatus.LTA, BookingStatus.CL}:
            continue
        agreement = find_best_matching_agreement(
            port_id=port.id,
            shipping_line_id=shipping_line.id,
            vessel=vessel,
            call_date=spec["call_date"],
            position=None,
        )
        if agreement is None:
            raise BookingBatchCreateError(
                "No hay un acuerdo LTA vigente que cubra esta reserva "
                f"({spec['call_date'].isoformat()}: puerto, naviera, barco y día).",
                "status",
            )

    existing_codes = set(
        Booking.objects.filter(booking_code__startswith=port.code.upper()).values_list(
            "booking_code",
            flat=True,
        )
    )

    bookings: list[Booking] = []
    reserved_by_date: dict[date, set[int]] = {}

    with transaction.atomic():
        for spec in specs:
            call_date = spec["call_date"]
            reserved = reserved_by_date.setdefault(call_date, set())
            position = resolve_booking_position(
                port,
                vessel,
                call_date,
                preferred_position_id=spec.get("position_id"),
                reserved_position_ids=reserved,
            )
            if position:
                reserved.update(related_position_ids(position.id))

            code = resolve_unique_booking_code(
                port,
                shipping_line,
                vessel,
                call_date,
                existing_codes,
            )
            existing_codes.add(code)
            bookings.append(
                Booking(
                    port=port,
                    shipping_line=shipping_line,
                    vessel=vessel,
                    position=position,
                    call_date=call_date,
                    booking_code=code,
                    status=spec["status"],
                    notes=notes,
                    eta=spec.get("eta"),
                    etd=spec.get("etd"),
                    planned_pax=spec.get("planned_pax"),
                    created_by=created_by,
                    long_term_agreement=None,
                )
            )

        for booking in bookings:
            agreement = find_best_matching_agreement(
                port_id=port.id,
                shipping_line_id=shipping_line.id,
                vessel=vessel,
                call_date=booking.call_date,
                position=booking.position,
            )
            booking.long_term_agreement = agreement
        Booking.objects.bulk_create(bookings)

    created = list(
        Booking.objects.filter(
            port=port,
            vessel=vessel,
            call_date__in=unique_dates,
        ).select_related("port", "shipping_line", "vessel", "position")
    )

    from apps.audit.services.record import record_booking_audit
    from apps.bookings.services.confirmation_pdf import (
        CONFIRMATION_PDF_STATUSES,
        save_confirmation_pdf,
    )

    for booking in created:
        summary = f"Reserva creada ({booking.get_status_display()})"
        if booking.position_id:
            summary = (
                f"{summary} — posición {booking.position.code} asignada automáticamente"
            )
        if booking.status in CONFIRMATION_PDF_STATUSES:
            save_confirmation_pdf(booking)
            booking.save(update_fields=["confirmation_pdf", "updated_at"])
        refresh_related_booking_conflicts(booking, user=created_by)
        record_booking_audit(
            booking,
            action="created",
            summary=summary,
            changes=audit_changes,
            user=created_by,
        )

    return created
