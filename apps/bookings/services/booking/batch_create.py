from datetime import date

from django.db import transaction

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.position_assignment import auto_assign_position
from apps.catalogs.models import Port, ShippingLine, Vessel


class BookingBatchCreateError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def create_booking_batch(
    *,
    port_id: int,
    shipping_line_id: int,
    vessel_id: int,
    call_dates: list[date],
    notes: str = "",
    created_by=None,
) -> list[Booking]:
    if not call_dates:
        raise BookingBatchCreateError("Selecciona al menos una fecha.", "call_dates")

    unique_dates = sorted({d for d in call_dates})
    if len(unique_dates) != len(call_dates):
        raise BookingBatchCreateError("Las fechas deben ser únicas.", "call_dates")

    try:
        port = Port.objects.get(pk=port_id, is_active=True)
    except Port.DoesNotExist:
        raise BookingBatchCreateError("Puerto no válido.", "port")

    try:
        shipping_line = ShippingLine.objects.get(pk=shipping_line_id, is_active=True)
    except ShippingLine.DoesNotExist:
        raise BookingBatchCreateError("Naviera no válida.", "shipping_line")

    try:
        vessel = Vessel.objects.select_related("shipping_line").get(
            pk=vessel_id,
            is_active=True,
        )
    except Vessel.DoesNotExist:
        raise BookingBatchCreateError("Barco no válido.", "vessel")

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

    from apps.bookings.services.validation import validate_booking_params

    validation = validate_booking_params(
        port_id=port.id,
        vessel_id=vessel.id,
        call_dates=unique_dates,
    )
    if not validation["valid"]:
        messages = "; ".join(e["message"] for e in validation["errors"])
        raise BookingBatchCreateError(messages, "call_dates")

    existing_codes = set(
        Booking.objects.filter(booking_code__startswith=port.code.upper()).values_list(
            "booking_code",
            flat=True,
        )
    )

    bookings: list[Booking] = []
    reserved_by_date: dict[date, set[int]] = {}

    with transaction.atomic():
        for call_date in unique_dates:
            reserved = reserved_by_date.setdefault(call_date, set())
            position = auto_assign_position(
                port,
                vessel,
                call_date,
                reserved_position_ids=reserved,
            )
            if position:
                reserved.add(position.id)

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
                    status=BookingStatus.NR,
                    notes=notes,
                    created_by=created_by,
                )
            )
        Booking.objects.bulk_create(bookings)

    created = list(
        Booking.objects.filter(
            port=port,
            vessel=vessel,
            call_date__in=unique_dates,
        ).select_related("port", "shipping_line", "vessel", "position")
    )

    from apps.audit.services.record import record_booking_audit

    for booking in created:
        summary = "Reserva creada"
        if booking.position_id:
            summary = f"Reserva creada — posición {booking.position.code} asignada automáticamente"
        record_booking_audit(
            booking,
            action="created",
            summary=summary,
            user=created_by,
        )

    return created
