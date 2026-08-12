from decimal import Decimal

from django.db import migrations, models


def seed_pop_e1e2_min_loa(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    for pos in Position.objects.filter(port__code="puerto_plata"):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        if suffix != "E1+E2":
            continue
        if pos.min_loa_m is None:
            pos.min_loa_m = Decimal("365.00")
            pos.save(update_fields=["min_loa_m", "updated_at"])


def unseed_pop_e1e2_min_loa(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    for pos in Position.objects.filter(port__code="puerto_plata"):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        if suffix == "E1+E2":
            pos.min_loa_m = None
            pos.save(update_fields=["min_loa_m", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0032_seed_pop_filo_nesting"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="min_loa_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Min LOA for combined slots (mega-ship threshold, e.g. 365 m).",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.RunPython(seed_pop_e1e2_min_loa, unseed_pop_e1e2_min_loa),
    ]
