from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0004_booking_cancellation_reason"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="booking",
            name="folio",
        ),
    ]
