# Generated manually for LTA cadence fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0012_booking_import_batch_retry_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="longtermagreement",
            name="interval_days",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Cadence in days (e.g. 15). Null = no cadence filter.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="longtermagreement",
            name="cadence_anchor",
            field=models.DateField(
                blank=True,
                help_text="First expected call date for interval_days matching.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="longtermagreement",
            name="advance_months_min",
            field=models.PositiveSmallIntegerField(
                default=18,
                help_text="Legacy far-horizon hint (seasonal windows are authoritative).",
            ),
        ),
        migrations.AlterField(
            model_name="longtermagreement",
            name="advance_months_max",
            field=models.PositiveSmallIntegerField(
                default=32,
                help_text="Legacy max months ahead hint (seasonal windows are authoritative).",
            ),
        ),
    ]
