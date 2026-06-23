from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0002_booking_operational_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="actual_crew",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
