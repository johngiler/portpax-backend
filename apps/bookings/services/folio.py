from apps.bookings.models import Booking


class FolioError(Exception):
    pass


def _folio_prefix(booking: Booking) -> str:
    port_part = booking.port.code.upper().replace("-", "")[:8]
    year = booking.call_date.year
    line_part = booking.shipping_line.code.upper().replace("-", "")[:12]
    return f"{port_part}-{year}-{line_part}"


def assign_folio(booking: Booking) -> str:
    if booking.folio:
        return booking.folio

    prefix = _folio_prefix(booking)
    existing = (
        Booking.objects.filter(folio__startswith=f"{prefix}-")
        .values_list("folio", flat=True)
    )
    max_seq = 0
    for folio in existing:
        try:
            seq = int(folio.rsplit("-", 1)[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            continue

    folio = f"{prefix}-{max_seq + 1:03d}"
    booking.folio = folio
    booking.save(update_fields=["folio", "updated_at"])
    return folio
