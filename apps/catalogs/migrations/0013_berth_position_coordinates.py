from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0012_port_coordinate_precision"),
    ]

    operations = [
        migrations.AddField(
            model_name="berth",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
        migrations.AddField(
            model_name="berth",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
        migrations.AddField(
            model_name="position",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
        migrations.AddField(
            model_name="position",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
    ]
