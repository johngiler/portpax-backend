from django.db import migrations, models
import django.db.models.deletion


def migrate_m2m_to_lines(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    PositionBollardLine = apps.get_model("catalogs", "PositionBollardLine")
    PositionFenderLine = apps.get_model("catalogs", "PositionFenderLine")

    for position in Position.objects.all().iterator():
        for bollard in position.port_bollards.all():
            PositionBollardLine.objects.create(
                position_id=position.id,
                port_bollard_id=bollard.id,
                quantity=bollard.quantity,
                sort_order=0,
            )
        for fender in position.port_fenders.all():
            PositionFenderLine.objects.create(
                position_id=position.id,
                port_fender_id=fender.id,
                quantity=fender.quantity,
                sort_order=0,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0020_position_inventory_m2m"),
    ]

    operations = [
        migrations.CreateModel(
            name="PositionBollardLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField()),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "port_bollard",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="position_lines",
                        to="catalogs.portbollard",
                    ),
                ),
                (
                    "position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bollard_lines",
                        to="catalogs.position",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="PositionFenderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField()),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "port_fender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="position_lines",
                        to="catalogs.portfender",
                    ),
                ),
                (
                    "position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fender_lines",
                        to="catalogs.position",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="positionbollardline",
            constraint=models.UniqueConstraint(
                fields=("position", "port_bollard"),
                name="uniq_position_bollard_line",
            ),
        ),
        migrations.AddConstraint(
            model_name="positionfenderline",
            constraint=models.UniqueConstraint(
                fields=("position", "port_fender"),
                name="uniq_position_fender_line",
            ),
        ),
        migrations.RunPython(migrate_m2m_to_lines, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="position",
            name="port_bollards",
        ),
        migrations.RemoveField(
            model_name="position",
            name="port_fenders",
        ),
    ]
