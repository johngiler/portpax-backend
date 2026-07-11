from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0003_booking_actual_crew"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="cancellation_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("bad_weather", "Mal tiempo"),
                    ("shipping_line_decision", "Decisión naviera"),
                    ("itm_decision", "Decisión ITM"),
                ],
                help_text="Reason selected when cancelling (provisional catalog).",
                max_length=40,
            ),
        ),
    ]
