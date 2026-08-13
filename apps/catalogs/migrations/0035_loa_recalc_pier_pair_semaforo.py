from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def migrate_loa_recalc_and_deactivate_combined(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Position = apps.get_model("catalogs", "Position")
    PositionComponent = apps.get_model("catalogs", "PositionComponent")
    PositionLoaRecalcRule = apps.get_model("catalogs", "PositionLoaRecalcRule")

    # Convert legacy combined-based rules to pier pairs.
    for rule in PositionLoaRecalcRule.objects.all():
        combined_id = getattr(rule, "combined_position_id", None)
        if not combined_id:
            continue
        links = list(
            PositionComponent.objects.filter(combined_position_id=combined_id).order_by(
                "sort_order"
            )
        )
        if len(links) < 2:
            rule.delete()
            continue
        combined = Position.objects.filter(pk=combined_id).first()
        max_loa = (
            combined.max_loa_m
            if combined and combined.max_loa_m is not None
            else Decimal("580.00")
        )
        sep = (
            rule.min_separation_m
            if rule.min_separation_m is not None
            else Decimal("15.00")
        )
        rule.position_a_id = links[0].source_position_id
        rule.position_b_id = links[1].source_position_id
        rule.max_loa_m = max_loa
        rule.separation_m = sep
        rule.yellow_from_m = max_loa + Decimal("1.00")
        rule.red_from_m = max_loa + Decimal("41.00")
        rule.save()

    # Deactivate all combined catalog positions (no longer bookable slots).
    combined_ids = set(
        PositionComponent.objects.values_list("combined_position_id", flat=True)
    )
    if combined_ids:
        Position.objects.filter(pk__in=combined_ids).update(is_active=False)

    # Ensure POP E1↔E2 rule exists with Fernanda defaults.
    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return
    try:
        e1 = Position.objects.get(port=port, code="puerto_plata-E1")
        e2 = Position.objects.get(port=port, code="puerto_plata-E2")
    except Position.DoesNotExist:
        return

    PositionLoaRecalcRule.objects.update_or_create(
        port=port,
        position_a=e1,
        position_b=e2,
        defaults={
            "max_loa_m": Decimal("580.00"),
            "separation_m": Decimal("15.00"),
            "yellow_from_m": Decimal("581.00"),
            "red_from_m": Decimal("621.00"),
            "is_active": True,
            "notes": "POP shared pier LOA E1↔E2 (Fernanda/Herman Aug 2026).",
        },
    )
    PositionLoaRecalcRule.objects.filter(
        port=port,
        position_a__isnull=True,
    ).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """Add pier-pair LOA recalc fields and backfill; schema cleanup in 0036."""

    # Postgres: UPDATE in RunPython + FK index creation cannot share one txn.
    atomic = False

    dependencies = [
        ("catalogs", "0034_position_loa_recalc_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="position_a",
            field=models.ForeignKey(
                help_text="First pier in the shared pair (e.g. E1).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="loa_recalc_rules_as_a",
                to="catalogs.position",
            ),
        ),
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="position_b",
            field=models.ForeignKey(
                help_text="Second pier in the shared pair (e.g. E2).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="loa_recalc_rules_as_b",
                to="catalogs.position",
            ),
        ),
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="max_loa_m",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("580.00"),
                help_text="Total pier max LOA shared by both positions (m).",
                max_digits=7,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="separation_m",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("15.00"),
                help_text="Gap reserved between the two ships (m).",
                max_digits=5,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="yellow_from_m",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("581.00"),
                help_text="Sum of both LOAs at or above this is yellow (m).",
                max_digits=7,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="positionloarecalcrule",
            name="red_from_m",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("621.00"),
                help_text="Sum of both LOAs at or above this is red (m).",
                max_digits=7,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(migrate_loa_recalc_and_deactivate_combined, noop_reverse),
    ]
