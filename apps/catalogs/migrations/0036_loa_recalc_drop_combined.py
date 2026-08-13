import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Drop legacy combined_position LOA recalc fields; enforce pier pair FKs."""

    atomic = False

    dependencies = [
        ("catalogs", "0035_loa_recalc_pier_pair_semaforo"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="positionloarecalcrule",
            name="uniq_position_loa_recalc_rule",
        ),
        migrations.RemoveField(
            model_name="positionloarecalcrule",
            name="combined_position",
        ),
        migrations.RemoveField(
            model_name="positionloarecalcrule",
            name="min_separation_m",
        ),
        migrations.AlterField(
            model_name="positionloarecalcrule",
            name="position_a",
            field=models.ForeignKey(
                help_text="First pier in the shared pair (e.g. E1).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="loa_recalc_rules_as_a",
                to="catalogs.position",
            ),
        ),
        migrations.AlterField(
            model_name="positionloarecalcrule",
            name="position_b",
            field=models.ForeignKey(
                help_text="Second pier in the shared pair (e.g. E2).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="loa_recalc_rules_as_b",
                to="catalogs.position",
            ),
        ),
        migrations.AddConstraint(
            model_name="positionloarecalcrule",
            constraint=models.UniqueConstraint(
                fields=("port", "position_a", "position_b"),
                name="uniq_position_loa_recalc_rule",
            ),
        ),
        migrations.AddConstraint(
            model_name="positionloarecalcrule",
            constraint=models.CheckConstraint(
                condition=~models.Q(position_a=models.F("position_b")),
                name="loa_recalc_positions_distinct",
            ),
        ),
        migrations.AlterModelOptions(
            name="positionloarecalcrule",
            options={"ordering": ["port", "position_a", "position_b"]},
        ),
    ]
