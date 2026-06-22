from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0013_berth_position_coordinates"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="position",
            name="out_of_service",
        ),
        migrations.RemoveField(
            model_name="position",
            name="is_projection",
        ),
    ]
