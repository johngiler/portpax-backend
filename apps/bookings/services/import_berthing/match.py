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
    return text


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


def resolve_vessel(
    ship_raw: str,
    shipping_line: ShippingLine,
    *,
    loa_m: object = None,
) -> Vessel | None:
    name = normalize_ship_name(ship_raw)
    if not name:
        return None

    qs = Vessel.objects.filter(shipping_line=shipping_line, is_active=True)
    loa = _as_loa(loa_m)

    exact = qs.filter(name__iexact=name).first()
    if exact:
        if loa is not None and exact.loa_m is None:
            exact.loa_m = loa
            exact.save(update_fields=["loa_m", "updated_at"])
        return exact

    starts = list(qs.filter(name__istartswith=name).order_by("name")[:5])
    if len(starts) == 1:
        vessel = starts[0]
        if loa is not None and vessel.loa_m is None:
            vessel.loa_m = loa
            vessel.save(update_fields=["loa_m", "updated_at"])
        return vessel

    contains = list(qs.filter(name__icontains=name).order_by("name")[:5])
    if len(contains) == 1:
        vessel = contains[0]
        if loa is not None and vessel.loa_m is None:
            vessel.loa_m = loa
            vessel.save(update_fields=["loa_m", "updated_at"])
        return vessel

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
