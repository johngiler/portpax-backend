from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0030_recompute_future_planned_pax_include_today"),
    ]

    operations = [
        migrations.AddField(
            model_name="longtermagreement",
            name="date_exceptions",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Date-only exceptions to weekday/cadence: "
                    "include {kind, date}, skip {kind, date}, "
                    "reschedule {kind, from, to}."
                ),
            ),
        ),
    ]
