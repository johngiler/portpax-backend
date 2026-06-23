from django.db import migrations

from apps.catalogs.utils.position_code import build_position_code, position_code_prefix


def prefix_position_codes(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    for position in Position.objects.select_related("port").iterator():
        prefix = position_code_prefix(position.port.code)
        if position.code.lower().startswith(prefix):
            continue
        position.code = build_position_code(position.port.code, position.code)
        position.save(update_fields=["code"])


def unprefix_position_codes(apps, schema_editor):
    Position = apps.get_model("catalogs", "Position")
    for position in Position.objects.select_related("port").iterator():
        prefix = position_code_prefix(position.port.code)
        if position.code.lower().startswith(prefix):
            position.code = position.code[len(prefix) :]
            position.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0016_shipping_line_vessel_logo"),
    ]

    operations = [
        migrations.RunPython(prefix_position_codes, unprefix_position_codes),
    ]
