from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def seed_pop_loa_recalc(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    PositionLoaRecalcRule = apps.get_model("catalogs", "PositionLoaRecalcRule")

    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return

    combined = None
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        if suffix == "E1+E2":
            combined = pos
            break
    if combined is None:
        return

    PositionLoaRecalcRule.objects.update_or_create(
        port=port,
        combined_position=combined,
        defaults={
            "min_separation_m": Decimal("15.00"),
            "is_active": True,
            "notes": "Shared LOA on E1/E2: remaining = combined max − occupant − 15 m.",
        },
    )


def unseed_pop_loa_recalc(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PositionLoaRecalcRule = apps.get_model("catalogs", "PositionLoaRecalcRule")
    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return
    PositionLoaRecalcRule.objects.filter(port=port).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0033_position_min_loa_m"),
    ]

    operations = [
        migrations.CreateModel(
            name="PositionLoaRecalcRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "min_separation_m",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("15.00"),
                        help_text="Gap reserved between the two ships (m).",
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0"))
                        ],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "combined_position",
                    models.ForeignKey(
                        help_text="Combined slot whose max LOA is shared (e.g. E1+E2).",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loa_recalc_rules",
                        to="catalogs.position",
                    ),
                ),
                (
                    "port",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="position_loa_recalc_rules",
                        to="catalogs.port",
                    ),
                ),
            ],
            options={
                "ordering": ["port", "combined_position"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("port", "combined_position"),
                        name="uniq_position_loa_recalc_rule",
                    )
                ],
            },
        ),
        migrations.RunPython(seed_pop_loa_recalc, unseed_pop_loa_recalc),
    ]
