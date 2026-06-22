from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0014_remove_position_status_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="PositionComponent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveSmallIntegerField(default=1)),
                (
                    "combined_position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="component_links",
                        to="catalogs.position",
                    ),
                ),
                (
                    "source_position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="used_in_combined",
                        to="catalogs.position",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "source_position__code"],
            },
        ),
        migrations.AddConstraint(
            model_name="positioncomponent",
            constraint=models.UniqueConstraint(
                fields=("combined_position", "source_position"),
                name="uniq_position_component_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="positioncomponent",
            constraint=models.UniqueConstraint(
                fields=("combined_position", "sort_order"),
                name="uniq_position_component_order",
            ),
        ),
    ]
