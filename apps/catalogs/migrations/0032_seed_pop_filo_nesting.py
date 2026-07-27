"""Seed FILO nesting for Puerto Plata E1 (outer) → E2 (inner)."""

from django.db import migrations


def seed_pop_filo(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    PositionNestingRule = apps.get_model("catalogs", "PositionNestingRule")

    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return

    try:
        outer = Position.objects.get(port=port, code="puerto_plata-E1")
        inner = Position.objects.get(port=port, code="puerto_plata-E2")
    except Position.DoesNotExist:
        return

    PositionNestingRule.objects.update_or_create(
        port=port,
        outer_position=outer,
        inner_position=inner,
        defaults={
            "enforce_eta": True,
            "enforce_etd": True,
            "is_active": True,
            "notes": "Taino Bay double parking: E1 first-in, E2 fondo.",
        },
    )


def unseed_pop_filo(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PositionNestingRule = apps.get_model("catalogs", "PositionNestingRule")
    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return
    PositionNestingRule.objects.filter(port=port).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0031_position_nesting_rule"),
    ]

    operations = [
        migrations.RunPython(seed_pop_filo, unseed_pop_filo),
    ]
