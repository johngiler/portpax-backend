"""Resolve / create catalog entities for berthing import rows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.utils.text import slugify

from apps.bookings.services.import_berthing.aliases import BRAND_TO_LINE_CODE, PORT_BY_KEY
from apps.catalogs.models import Port, Position, ShippingLine, ShippingLineGroup, Vessel

IMPORTED_GROUP_CODE = "imported_berthing"
IMPORTED_GROUP_NAME = "Imported (Berthing)"


@dataclass
class MatchStats:
    lines_created: int = 0
    vessels_created: int = 0
    positions_null: int = 0
    created_lines: list[str] = field(default_factory=list)
    created_vessels: list[str] = field(default_factory=list)


def _unique_slug(model, base: str, *, field: str = "code") -> str:
    slug = slugify(base)[:60] or "item"
    if not model.objects.filter(**{field: slug}).exists():
        return slug
    n = 2
    while model.objects.filter(**{field: f"{slug}_{n}"}).exists():
        n += 1
    return f"{slug}_{n}"


def normalize_ship_name(raw: str) -> str:
    text = re.sub(r"\([^)]*\)", "", raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_port(port_key: str) -> Port:
    code = PORT_BY_KEY[port_key]
    return Port.objects.get(code=code)


def _imported_group() -> ShippingLineGroup:
    group, _ = ShippingLineGroup.objects.get_or_create(
        code=IMPORTED_GROUP_CODE,
        defaults={"name": IMPORTED_GROUP_NAME},
    )
    return group


def resolve_shipping_line(
    brand: str | None,
    corp: str | None,
    stats: MatchStats,
) -> ShippingLine:
    keys = [k for k in (brand, corp) if k]
    for key in keys:
        mapped = BRAND_TO_LINE_CODE.get(key.upper())
        if mapped:
            line = ShippingLine.objects.filter(code=mapped).first()
            if line:
                return line
        line = ShippingLine.objects.filter(code__iexact=key).first()
        if line:
            return line
        line = ShippingLine.objects.filter(name__iexact=key).first()
        if line:
            return line
        line = (
            ShippingLine.objects.filter(name__icontains=key)
            .order_by("name")
            .first()
        )
        if line and len(key) >= 3:
            return line

    label = (brand or corp or "UNKNOWN").strip().upper()
    code = _unique_slug(ShippingLine, label)
    line, created = ShippingLine.objects.get_or_create(
        code=code,
        defaults={
            "name": label.title() if len(label) > 3 else label,
            "group": _imported_group(),
        },
    )
    if created:
        stats.lines_created += 1
        stats.created_lines.append(line.code)
    return line


def resolve_vessel(
    ship_raw: str,
    shipping_line: ShippingLine,
    stats: MatchStats,
) -> Vessel:
    name = normalize_ship_name(ship_raw)
    qs = Vessel.objects.filter(shipping_line=shipping_line)

    exact = qs.filter(name__iexact=name).first()
    if exact:
        return exact

    starts = list(qs.filter(name__istartswith=name).order_by("name")[:5])
    if len(starts) == 1:
        return starts[0]

    contains = list(qs.filter(name__icontains=name).order_by("name")[:5])
    if len(contains) == 1:
        return contains[0]

    # Prefer unambiguous global match under same brand tokens
    global_exact = Vessel.objects.filter(name__iexact=name).first()
    if global_exact and global_exact.shipping_line_id == shipping_line.id:
        return global_exact

    vessel, created = Vessel.objects.get_or_create(
        shipping_line=shipping_line,
        name=name,
        defaults={},
    )
    if created:
        stats.vessels_created += 1
        stats.created_vessels.append(f"{shipping_line.code}:{name}")
    return vessel


def resolve_position(port: Port, berth_assign: str | None, stats: MatchStats) -> Position | None:
    if not berth_assign:
        stats.positions_null += 1
        return None
    code = berth_assign.strip().upper()
    position = (
        Position.objects.filter(port=port, code__iexact=code).first()
        or Position.objects.filter(port=port, code__iendswith=f"-{code}").first()
        or Position.objects.filter(port=port, code__icontains=code).first()
    )
    if position is None:
        stats.positions_null += 1
    return position
