import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0018_port_fender"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="port_bollard",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="positions",
                to="catalogs.portbollard",
            ),
        ),
        migrations.AddField(
            model_name="position",
            name="port_fender",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="positions",
                to="catalogs.portfender",
            ),
        ),
    ]
