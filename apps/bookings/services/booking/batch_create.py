from datetime import date

from django.db import transaction

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
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

    existing_codes = set(
        Booking.objects.filter(booking_code__startswith=port.code.upper()).values_list(
            "booking_code",
            flat=True,
        )
    )

    bookings: list[Booking] = []

    with transaction.atomic():
        for call_date in unique_dates:
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
                    call_date=call_date,
                    booking_code=code,
                    status=BookingStatus.REQUESTED,
                    notes=notes,
                    created_by=created_by,
                )
            )
        Booking.objects.bulk_create(bookings)

    return list(
        Booking.objects.filter(
            port=port,
            vessel=vessel,
            call_date__in=unique_dates,
        ).select_related("port", "shipping_line", "vessel")
    )
