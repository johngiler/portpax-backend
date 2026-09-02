"""Backfill planned_pax for Real bookings imported without it."""

from django.db import migrations


def forwards(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    Vessel = apps.get_model("catalogs", "Vessel")
    for vessel_id, capacity in (
        Vessel.objects.filter(pax_capacity__isnull=False).values_list(
            "id", "pax_capacity"
        )
    ):
        Booking.objects.filter(
            status="r",
            planned_pax__isnull=True,
            vessel_id=vessel_id,
        ).update(planned_pax=capacity)


def backwards(apps, schema_editor):
    # Irreversible data fill; leave planned_pax as-is.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0026_booking_operation_notes"),
        ("catalogs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
