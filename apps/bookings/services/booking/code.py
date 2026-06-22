import re

from apps.catalogs.models import Port, ShippingLine, Vessel


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
    date_part = call_date.strftime("%Y%m%d")
    return (
        f"{port.code.upper()}-{shipping_line.code.upper()}-"
        f"{_vessel_code_part(vessel)}-{date_part}"
    )


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
    while f"{base}-{suffix}" in existing_codes:
        suffix += 1
    return f"{base}-{suffix}"
