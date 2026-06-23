from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0016_shipping_line_vessel_logo"),
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="actual_pax",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancellation_evidence",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="bookings/cancellation_evidence/",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="confirmation_pdf",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="bookings/confirmations/",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="eta",
            field=models.TimeField(blank=True, help_text="Estimated time of arrival.", null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="etd",
            field=models.TimeField(blank=True, help_text="Estimated time of departure.", null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="folio",
            field=models.CharField(
                blank=True,
                help_text="Port + year + shipping line + sequential (assigned on confirm).",
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="planned_pax",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="position",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="bookings",
                to="catalogs.position",
            ),
        ),
    ]
