from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0011_fix_roatan_coordinates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="port",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
        migrations.AlterField(
            model_name="port",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=11, null=True
            ),
        ),
    ]
