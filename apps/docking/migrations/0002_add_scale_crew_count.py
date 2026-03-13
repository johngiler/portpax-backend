# Generated manually - add crew_count to Scale

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="scale",
            name="crew_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
