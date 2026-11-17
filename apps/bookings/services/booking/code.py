import re

from apps.catalogs.models import Port, ShippingLine, Vessel

# Booking.booking_code CharField(max_length=64)
MAX_BOOKING_CODE_LEN = 64
# Reserve for uniqueness suffix "-2" … "-999"
_SUFFIX_RESERVE = 4


def _vessel_code_part(vessel: Vessel) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", vessel.name.upper())
    if compact:
        return compact[:12]
    return f"V{vessel.id}"


def build_booking_code_base(
    port: Port,
    shipping_line: ShippingLine,
    vessel: Vessel,
    call_date,
) -> str:
    """PORT-LINE-VESSEL-YYYYMMDD, truncated to fit max_length (and suffix room)."""
    date_part = call_date.strftime("%Y%m%d")
    port_part = port.code.upper()
    line_part = shipping_line.code.upper()
    vessel_part = _vessel_code_part(vessel)

    # Fixed tail keeps vessel + date readable for ops.
    tail = f"-{vessel_part}-{date_part}"
    max_head = MAX_BOOKING_CODE_LEN - _SUFFIX_RESERVE - len(tail)
    if max_head < 8:
        max_head = MAX_BOOKING_CODE_LEN - len(tail)

    # Prefer full port code; truncate shipping-line slug first.
    max_port = min(len(port_part), max(8, max_head // 2))
    port_fit = port_part[:max_port]
    max_line = max_head - len(port_fit) - 1
    if max_line < 1:
        port_fit = port_part[: max(1, max_head - 2)]
        max_line = max(1, max_head - len(port_fit) - 1)
    line_fit = line_part[:max_line]
    base = f"{port_fit}-{line_fit}{tail}"
    return base[:MAX_BOOKING_CODE_LEN]


def resolve_unique_booking_code(
    port: Port,
    shipping_line: ShippingLine,
    vessel: Vessel,
    call_date,
    existing_codes: set[str],
) -> str:
    base = build_booking_code_base(port, shipping_line, vessel, call_date)
    if base not in existing_codes:
        return base

    suffix = 2
    while True:
        marker = f"-{suffix}"
        head = base[: MAX_BOOKING_CODE_LEN - len(marker)]
        candidate = f"{head}{marker}"
        if candidate not in existing_codes:
            return candidate
        suffix += 1
