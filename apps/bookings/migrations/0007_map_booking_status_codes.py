from django.db import migrations


STATUS_MAP = {
    "requested": "nr",
    "confirmed": "co",
    "cancelled": "c",
}


def map_legacy_statuses(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    for old, new in STATUS_MAP.items():
        Booking.objects.filter(status=old).update(status=new)


def reverse_map_statuses(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    reverse = {v: k for k, v in STATUS_MAP.items()}
    for new, old in reverse.items():
        Booking.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0006_booking_eta_real_booking_etd_real_and_more"),
    ]

    operations = [
        migrations.RunPython(map_legacy_statuses, reverse_map_statuses),
    ]
