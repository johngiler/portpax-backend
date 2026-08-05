"""Seed four MSC cadence LTAs (Especificaciones LTA´s / meet).

Roatán Muelle 2 → position code roatan-P2.
Puerto Plata Muelle 2 → position code puerto_plata-E2 (ops label on M1_M2 berth).
"""

from datetime import date

from django.db import migrations

MSC_LTA_CODES = [
    "msc-roatan-seascape-thu",
    "msc-roatan-world-america-mon",
    "msc-pop-world-america-mon",
    "msc-pop-grandiosa-wed",
]


def seed_msc_ltas(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    ShippingLine = apps.get_model("catalogs", "ShippingLine")
    Vessel = apps.get_model("catalogs", "Vessel")
    LongTermAgreement = apps.get_model("bookings", "LongTermAgreement")

    try:
        line = ShippingLine.objects.get(code="msc_cruises")
    except ShippingLine.DoesNotExist:
        return

    try:
        roatan = Port.objects.get(code="roatan")
        pop = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return

    vessels = {
        name: Vessel.objects.filter(shipping_line=line, name=name).first()
        for name in ("Seascape", "World America", "Grandiosa")
    }
    if not all(vessels.values()):
        return

    pos_roatan = Position.objects.filter(port=roatan, code="roatan-P2").first()
    pos_pop = Position.objects.filter(port=pop, code="puerto_plata-E2").first()

    specs = [
        {
            "code": "msc-roatan-seascape-thu",
            "name": "MSC Roatán — Seascape jueves cada 15 días",
            "port": roatan,
            "vessel": vessels["Seascape"],
            "position": pos_roatan,
            "weekdays": [3],  # Thursday
            "interval_days": 15,
            "cadence_anchor": date(2025, 11, 13),
            "valid_from": date(2025, 11, 13),
            "valid_until": date(2030, 4, 25),
            "notes": (
                "Especificaciones LTA: Roatán Seascape jueves cada 15 días, "
                "Muelle 2, 13 nov 2025 – 25 abr 2030."
            ),
        },
        {
            "code": "msc-roatan-world-america-mon",
            "name": "MSC Roatán — World America lunes cada 15 días",
            "port": roatan,
            "vessel": vessels["World America"],
            "position": pos_roatan,
            "weekdays": [0],  # Monday
            "interval_days": 15,
            "cadence_anchor": date(2025, 11, 10),
            "valid_from": date(2025, 11, 10),
            "valid_until": date(2030, 4, 22),
            "notes": (
                "Especificaciones LTA: Roatán World America lunes cada 15 días, "
                "Muelle 2, 10 nov 2025 – 22 abr 2030."
            ),
        },
        {
            "code": "msc-pop-world-america-mon",
            "name": "MSC Puerto Plata — World America lunes cada 15 días",
            "port": pop,
            "vessel": vessels["World America"],
            "position": pos_pop,
            "weekdays": [0],
            "interval_days": 15,
            "cadence_anchor": date(2025, 11, 17),
            "valid_from": date(2025, 11, 17),
            "valid_until": date(2030, 4, 29),
            "notes": (
                "Especificaciones LTA: Puerto Plata World America lunes cada 15 días, "
                "Muelle 2, 17 nov 2025 – 29 abr 2030."
            ),
        },
        {
            "code": "msc-pop-grandiosa-wed",
            "name": "MSC Puerto Plata — Grandiosa miércoles cada 15 días",
            "port": pop,
            "vessel": vessels["Grandiosa"],
            "position": pos_pop,
            "weekdays": [2],  # Wednesday
            "interval_days": 15,
            "cadence_anchor": date(2026, 4, 1),
            "valid_from": date(2026, 4, 1),
            "valid_until": date(2030, 4, 24),
            "notes": (
                "Especificaciones LTA: Puerto Plata Grandiosa miércoles cada 15 días, "
                "Muelle 2, 1 abr 2026 – 24 abr 2030."
            ),
        },
    ]

    for spec in specs:
        vessel = spec.pop("vessel")
        position = spec.pop("position")
        agreement, _created = LongTermAgreement.objects.update_or_create(
            code=spec["code"],
            defaults={
                **spec,
                "shipping_line": line,
                "all_vessels": False,
                "min_packs": None,
                "advance_months_min": 18,
                "advance_months_max": 32,
                "is_active": True,
            },
        )
        agreement.vessels.set([vessel])
        if position is not None:
            agreement.positions.set([position])
        else:
            agreement.positions.clear()


def unseed_msc_ltas(apps, schema_editor):
    LongTermAgreement = apps.get_model("bookings", "LongTermAgreement")
    LongTermAgreement.objects.filter(code__in=MSC_LTA_CODES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0013_lta_cadence_fields"),
        ("catalogs", "0032_seed_pop_filo_nesting"),
    ]

    operations = [
        migrations.RunPython(seed_msc_ltas, unseed_msc_ltas),
    ]
