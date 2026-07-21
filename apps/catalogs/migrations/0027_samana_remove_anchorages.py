"""Remove Samaná anchorage positions: layout plans show a pier-only terminal."""

from django.db import migrations


def remove_anchorages(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    Position.objects.filter(
        port=port,
        code__in=["samana-A1", "samana-A2"],
        position_type="anchorage",
    ).delete()

    if port.anchorage_slot_count:
        port.anchorage_slot_count = 0
        port.save(update_fields=["anchorage_slot_count", "updated_at"])


def restore_anchorages(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    for code, sort_order in (("samana-A1", 3), ("samana-A2", 4)):
        Position.objects.get_or_create(
            port=port,
            code=code,
            defaults={
                "position_type": "anchorage",
                "sort_order": sort_order,
                "is_active": True,
            },
        )
    port.anchorage_slot_count = 2
    port.save(update_fields=["anchorage_slot_count", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0026_samana_jan_2027_scenario_name"),
    ]

    operations = [
        migrations.RunPython(remove_anchorages, restore_anchorages),
    ]
