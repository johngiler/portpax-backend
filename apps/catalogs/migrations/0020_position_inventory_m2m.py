from django.db import migrations, models


def copy_fk_to_m2m(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    for position in Position.objects.exclude(port_bollard_id__isnull=True).iterator():
        position.port_bollards.add(position.port_bollard_id)
    for position in Position.objects.exclude(port_fender_id__isnull=True).iterator():
        position.port_fenders.add(position.port_fender_id)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0019_position_inventory_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="port_bollards",
            field=models.ManyToManyField(
                blank=True,
                related_name="positions",
                to="catalogs.portbollard",
            ),
        ),
        migrations.AddField(
            model_name="position",
            name="port_fenders",
            field=models.ManyToManyField(
                blank=True,
                related_name="positions",
                to="catalogs.portfender",
            ),
        ),
        migrations.RunPython(copy_fk_to_m2m, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="position",
            name="port_bollard",
        ),
        migrations.RemoveField(
            model_name="position",
            name="port_fender",
        ),
    ]
