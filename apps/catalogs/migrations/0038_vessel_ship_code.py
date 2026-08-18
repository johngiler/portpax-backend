from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0037_alter_position_min_loa_m"),
    ]

    operations = [
        migrations.AddField(
            model_name="vessel",
            name="ship_code",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
