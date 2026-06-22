from decimal import Decimal

from django.db import migrations


def fix_roatan_coordinates(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Port.objects.filter(code="roatan").update(
        latitude=Decimal("16.308333"),
        longitude=Decimal("-86.591667"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0010_berth_image"),
    ]

    operations = [
        migrations.RunPython(fix_roatan_coordinates, migrations.RunPython.noop),
    ]
