"""Resolve catalog entities for berthing import rows (match-only, no creates)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from apps.bookings.services.import_berthing.aliases import (
    BERTH_ALIAS_BY_PORT_CODE,
    BRAND_TO_LINE_CODE,
    PORT_BY_KEY,
)
from apps.catalogs.models import Port, Position, ShippingLine, Vessel


def normalize_ship_name(raw: str) -> str:
    text = re.sub(r"\([^)]*\)", "", raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ship_name_candidates(
    ship_raw: str,
    *,
    brand: str | None = None,
    corp: str | None = None,
) -> list[str]:
    """Return ordered unique ship names to try against the vessel catalog."""
    base = normalize_ship_name(ship_raw)
    if not base:
        return []

    candidates: list[str] = [base]

    # Bidirectional OTS ↔ "of the Seas" (catalog may use either form).
    if re.search(r"\s+OTS$", base, flags=re.IGNORECASE):
        candidates.append(
            re.sub(r"\s+OTS$", " of the Seas", base, flags=re.IGNORECASE).strip()
        )
    elif re.search(r"\s+of the Seas$", base, flags=re.IGNORECASE):
        candidates.append(
            re.sub(r"\s+of the Seas$", " OTS", base, flags=re.IGNORECASE).strip()
        )

    # Strip brand/corp prefix when Excel still has "USCG Mohawk" but catalog is "Mohawk".
    prefixes = [
        (brand or "").strip(),
        (corp or "").strip(),
        "USCG",
        "USCGC",
    ]
    for prefix in prefixes:
        if not prefix:
            continue
        pattern = re.compile(rf"^{re.escape(prefix)}\s+", re.IGNORECASE)
        for source in list(candidates):
            stripped = pattern.sub("", source).strip()
            if stripped and stripped.casefold() != source.casefold():
                candidates.append(stripped)

    seen: set[str] = set()
    ordered: list[str] = []
    for name in candidates:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


def resolve_port(port_key: str) -> Port:
    code = PORT_BY_KEY[port_key]
    return Port.objects.get(code=code, is_active=True)


def resolve_shipping_line(brand: str | None, corp: str | None) -> ShippingLine | None:
    keys = [k.strip() for k in (brand, corp) if k and str(k).strip()]
    seen: set[str] = set()
    for key in keys:
        upper = key.upper()
        if upper in seen:
            continue
        seen.add(upper)

        mapped = BRAND_TO_LINE_CODE.get(upper)
        if mapped:
            line = ShippingLine.objects.filter(code=mapped, is_active=True).first()
            if line:
                return line

        line = ShippingLine.objects.filter(code__iexact=key, is_active=True).first()
        if line:
            return line

        line = ShippingLine.objects.filter(name__iexact=key, is_active=True).first()
        if line:
            return line

    return None


def _as_loa(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        num = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return num if num > 0 else None


def _apply_loa_if_missing(vessel: Vessel, loa: Decimal | None) -> Vessel:
    if loa is not None and vessel.loa_m is None:
        vessel.loa_m = loa
        vessel.save(update_fields=["loa_m", "updated_at"])
    return vessel


def resolve_vessel(
    ship_raw: str,
    shipping_line: ShippingLine,
    *,
    loa_m: object = None,
    brand: str | None = None,
    corp: str | None = None,
) -> Vessel | None:
    candidates = ship_name_candidates(ship_raw, brand=brand, corp=corp)
    if not candidates:
        return None

    qs = Vessel.objects.filter(shipping_line=shipping_line, is_active=True)
    loa = _as_loa(loa_m)

    for name in candidates:
        exact = qs.filter(name__iexact=name).first()
        if exact:
            return _apply_loa_if_missing(exact, loa)

        starts = list(qs.filter(name__istartswith=name).order_by("name")[:5])
        if len(starts) == 1:
            return _apply_loa_if_missing(starts[0], loa)

        contains = list(qs.filter(name__icontains=name).order_by("name")[:5])
        if len(contains) == 1:
            return _apply_loa_if_missing(contains[0], loa)

    return None


def _find_position_by_short(port: Port, short: str) -> Position | None:
    """Match catalog position by short suffix (E1, N1, …) or full code."""
    short = short.strip().upper()
    return (
        Position.objects.filter(port=port, is_active=True, code__iexact=short).first()
        or Position.objects.filter(
            port=port, is_active=True, code__iexact=f"{port.code}-{short}"
        ).first()
        or Position.objects.filter(
            port=port, is_active=True, code__iendswith=f"-{short}"
        ).first()
    )


def resolve_position(port: Port, berth_assign: str | None) -> Position | None:
    if not berth_assign:
        return None

    raw = berth_assign.strip().upper()
    alias_map = BERTH_ALIAS_BY_PORT_CODE.get(port.code, {})
    preferred = alias_map.get(raw, raw)

    for short in dict.fromkeys([preferred, raw]):
        position = _find_position_by_short(port, short)
        if position:
            return position

    return None
