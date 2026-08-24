"""Auto-generated LTA agreement code and display name."""

from __future__ import annotations

import re
import unicodedata

from apps.bookings.models import LongTermAgreement
from apps.catalogs.models import Port, ShippingLine, Vessel

PORT_LTA_SEGMENT: dict[str, str] = {
    "puerto_plata": "pop",
    "roatan": "roatan",
    "cabo_rojo": "cabo-rojo",
    "la_paz": "la-paz",
    "melilla": "melilla",
    "samana": "samana",
}

WEEKDAY_CODE = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_LABEL_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def _slugify_segment(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    ascii_only = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower().strip())
    return slug.strip("-")


def _shipping_line_segment(code: str) -> str:
    key = code.strip().lower()
    first = key.split("_", 1)[0]
    return first or _slugify_segment(key)


def _port_segment(port_code: str) -> str:
    key = port_code.strip().lower()
    return PORT_LTA_SEGMENT.get(key) or _slugify_segment(key.replace("_", "-"))


def _vessel_segment(*, all_vessels: bool, vessel_names: list[str]) -> str | None:
    if all_vessels:
        return "all"
    if not vessel_names:
        return None
    if len(vessel_names) == 1:
        return _slugify_segment(vessel_names[0])
    return "-".join(sorted(_slugify_segment(n) for n in vessel_names))


def _weekday_segment(weekdays: list[int]) -> str | None:
    if not weekdays:
        return None
    parts = [
        WEEKDAY_CODE[d]
        for d in sorted(weekdays)
        if isinstance(d, int) and 0 <= d <= 6
    ]
    return "-".join(parts) if parts else None


def build_lta_agreement_code(
    *,
    shipping_line_code: str,
    port_code: str,
    all_vessels: bool,
    vessel_names: list[str],
    weekdays: list[int],
) -> str | None:
    """e.g. msc-pop-grandiosa-wed"""
    line = _shipping_line_segment(shipping_line_code)
    port = _port_segment(port_code)
    vessel = _vessel_segment(all_vessels=all_vessels, vessel_names=vessel_names)
    if not line or not port or not vessel:
        return None
    parts = [line, port, vessel]
    weekday = _weekday_segment(weekdays)
    if weekday:
        parts.append(weekday)
    return "-".join(parts)


def build_lta_agreement_name(
    *,
    shipping_line_name: str,
    port_name: str,
    all_vessels: bool,
    vessel_names: list[str],
    weekdays: list[int],
    interval_days: int | None,
) -> str | None:
    """e.g. MSC Puerto Plata — Grandiosa miércoles cada 15 días"""
    if not shipping_line_name.strip() or not port_name.strip():
        return None
    if all_vessels:
        vessel_part = "Todos los barcos"
    elif not vessel_names:
        return None
    elif len(vessel_names) == 1:
        vessel_part = vessel_names[0]
    else:
        vessel_part = ", ".join(vessel_names)

    weekday_labels = [
        WEEKDAY_LABEL_ES[d]
        for d in sorted(weekdays)
        if isinstance(d, int) and 0 <= d <= 6
    ]
    detail = vessel_part
    if weekday_labels:
        detail = f"{detail} {', '.join(weekday_labels)}"
    if interval_days is not None and interval_days > 0:
        detail = f"{detail} cada {interval_days} días"
    return f"{shipping_line_name.strip()} {port_name.strip()} — {detail}"


def allocate_unique_lta_code(base: str) -> str:
    """Return base or base-2, base-3, … if the slug is already taken."""
    base = base[:64]
    if not LongTermAgreement.objects.filter(code=base).exists():
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        if not LongTermAgreement.objects.filter(code=candidate).exists():
            return candidate
        n += 1


def build_identity_for_create(
    *,
    port: Port,
    shipping_line: ShippingLine,
    all_vessels: bool,
    vessels: list[Vessel],
    weekdays: list[int],
    interval_days: int | None,
) -> tuple[str, str]:
    vessel_names = [v.name for v in vessels]
    code = build_lta_agreement_code(
        shipping_line_code=shipping_line.code,
        port_code=port.code,
        all_vessels=all_vessels,
        vessel_names=vessel_names,
        weekdays=weekdays,
    )
    name = build_lta_agreement_name(
        shipping_line_name=shipping_line.name,
        port_name=port.name,
        all_vessels=all_vessels,
        vessel_names=vessel_names,
        weekdays=weekdays,
        interval_days=interval_days,
    )
    if not code or not name:
        raise ValueError(
            "No se pudo generar código/nombre: completa naviera, puerto y barco."
        )
    return allocate_unique_lta_code(code), name
