"""Align Samaná phase-1 mooring scenario with January 2027 layout caption."""

from datetime import date

from django.db import migrations

OLD_PHASE1_NAME = "2 vessels — Dec 2026 / Jan 2027"
NEW_PHASE1_NAME = "2 vessels — Jan 2027"


def rename_phase1(apps, schema_editor):
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    Port = apps.get_model("catalogs", "Port")
    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    scenario = MooringScenario.objects.filter(port=port, name=OLD_PHASE1_NAME).first()
    if not scenario:
        return
    if MooringScenario.objects.filter(port=port, name=NEW_PHASE1_NAME).exists():
        scenario.delete()
        return

    scenario.name = NEW_PHASE1_NAME
    scenario.effective_from = date(2027, 1, 1)
    scenario.notes = (
        "From Port Samaná mooring layout — January 2027 two-ship configuration "
        "(S1 365 m + N2 333 m)."
    )
    scenario.save(update_fields=["name", "effective_from", "notes", "updated_at"])


def revert_rename(apps, schema_editor):
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    Port = apps.get_model("catalogs", "Port")
    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    scenario = MooringScenario.objects.filter(port=port, name=NEW_PHASE1_NAME).first()
    if not scenario:
        return
    scenario.name = OLD_PHASE1_NAME
    scenario.effective_from = date(2026, 12, 1)
    scenario.notes = (
        "From Samaná pier layout — Dec 2026 / Jan 2027 two-ship configuration "
        "(S1 365 m + N2 333 m)."
    )
    scenario.save(update_fields=["name", "effective_from", "notes", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0025_enrich_samana_layouts"),
    ]

    operations = [
        migrations.RunPython(rename_phase1, revert_rename),
    ]
