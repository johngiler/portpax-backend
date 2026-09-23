from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0037_booking_first_arrival"),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="cancellation_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("bad_weather", "Mal tiempo"),
                    ("shipping_line_decision", "Decisión naviera"),
                    ("itm_decision", "Decisión ITM"),
                    ("lta_claimed", "Reclamo LTA"),
                ],
                help_text="Reason selected when cancelling (provisional catalog).",
                max_length=40,
            ),
        ),
    ]
