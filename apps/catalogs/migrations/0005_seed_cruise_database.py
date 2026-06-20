"""Seed shipping lines and vessels from backend/data/cruise_database.json (Base_Datos_Cruceros.xlsx)."""

import json
import re
from decimal import Decimal
from pathlib import Path

from django.db import migrations


def _slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_/]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64] or "unknown"


def _unique_slug(model, base: str) -> str:
    slug = _slugify(base)
    if not model.objects.filter(code=slug).exists():
        return slug
    n = 2
    while model.objects.filter(code=f"{slug}_{n}").exists():
        n += 1
    return f"{slug}_{n}"[:64]


def _dec(value):
    return Decimal(str(value)) if value is not None else None


def seed_cruise_database(apps, schema_editor):
    ShippingLineGroup = apps.get_model("catalogs", "ShippingLineGroup")
    ShippingLine = apps.get_model("catalogs", "ShippingLine")
    Vessel = apps.get_model("catalogs", "Vessel")

    data_path = Path(__file__).resolve().parents[3] / "data" / "cruise_database.json"
    with data_path.open(encoding="utf-8") as f:
        records = json.load(f)

    groups: dict[str, object] = {}
    lines: dict[tuple[str, str], object] = {}

    for row in records:
        group_name = row["group_name"]
        line_name = row["line_name"]

        if group_name not in groups:
            groups[group_name] = ShippingLineGroup.objects.create(
                code=_unique_slug(ShippingLineGroup, group_name),
                name=group_name,
            )

        line_key = (group_name, line_name)
        if line_key not in lines:
            lines[line_key] = ShippingLine.objects.create(
                group=groups[group_name],
                code=_unique_slug(ShippingLine, line_name),
                name=line_name,
            )

        Vessel.objects.create(
            shipping_line=lines[line_key],
            name=row["name"],
            vessel_class=row.get("vessel_class") or "",
            gross_tonnage=_dec(row.get("gross_tonnage")),
            pax_capacity=row.get("pax_capacity"),
            crew_capacity=row.get("crew_capacity"),
            loa_m=_dec(row.get("loa_m")),
            beam_m=_dec(row.get("beam_m")),
            draft_m=_dec(row.get("draft_m")),
            flag=row.get("flag") or "",
            year_built=row.get("year_built"),
            segment=row.get("segment") or "",
            size_category=row.get("size_category") or "",
            mooring_line_count=row.get("mooring_line_count"),
            bollard_count=row.get("bollard_count"),
            bollard_swl_t=_dec(row.get("bollard_swl_t")),
        )


def unseed_cruise_database(apps, schema_editor):
    Vessel = apps.get_model("catalogs", "Vessel")
    ShippingLine = apps.get_model("catalogs", "ShippingLine")
    ShippingLineGroup = apps.get_model("catalogs", "ShippingLineGroup")
    Vessel.objects.all().delete()
    ShippingLine.objects.all().delete()
    ShippingLineGroup.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0004_shipping_lines_and_vessels"),
    ]

    operations = [
        migrations.RunPython(seed_cruise_database, unseed_cruise_database),
    ]
