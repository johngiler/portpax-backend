"""Seed port bollard inventory and fender totals from docs/muelles_especificaciones.html §4."""

from django.db import migrations


def seed_bollards(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PortBollard = apps.get_model("catalogs", "PortBollard")

    inventory = {
        "puerto_plata": {
            "fender_count": 24,
            "bollards": [
                (200, "standard", 7, ""),
                (150, "standard", 22, ""),
                (75, "standard", 15, ""),
            ],
        },
        "roatan": {
            "fender_count": 16,
            "bollards": [
                (200, "standard", 9, ""),
                (150, "standard", 15, ""),
                (75, "standard", 7, ""),
            ],
        },
        "samana": {
            "fender_count": 18,
            "bollards": [
                (200, "standard", 24, ""),
                (100, "standard", 10, ""),
            ],
        },
        "cabo_rojo": {
            "fender_count": 24,
            "bollards": [
                (200, "standard", 27, ""),
            ],
        },
        "la_paz": {
            "fender_count": 6,
            "bollards": [
                (200, "standard", 2, ""),
                (150, "standard", 2, ""),
                (100, "standard", 13, ""),
                (50, "standard", 2, ""),
            ],
        },
        "melilla": {
            "fender_count": 20,
            "bollards": [
                (200, "quick_release", 12, "QRH"),
                (200, "t_head", 9, "T-head"),
                (200, "single_bitt", 5, "Single bitt"),
            ],
        },
    }

    sort = 0
    for code, data in inventory.items():
        try:
            port = Port.objects.get(code=code)
        except Port.DoesNotExist:
            continue
        port.fender_count = data["fender_count"]
        port.save(update_fields=["fender_count"])
        for capacity_t, bollard_type, quantity, label in data["bollards"]:
            sort += 1
            PortBollard.objects.create(
                port=port,
                capacity_t=capacity_t,
                bollard_type=bollard_type,
                quantity=quantity,
                label=label,
                sort_order=sort,
            )


def unseed_bollards(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PortBollard = apps.get_model("catalogs", "PortBollard")
    codes = ["puerto_plata", "roatan", "samana", "cabo_rojo", "la_paz", "melilla"]
    PortBollard.objects.filter(port__code__in=codes).delete()
    Port.objects.filter(code__in=codes).update(fender_count=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0008_port_assets_and_bollards"),
    ]

    operations = [
        migrations.RunPython(seed_bollards, unseed_bollards),
    ]
