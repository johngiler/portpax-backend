from django.db import migrations


def refresh_multi_port_conflict_snapshots(apps, schema_editor):
    """Rebuild proximity conflict messages with geo formula detail."""
    from apps.bookings.models import Booking
    from apps.bookings.services.validation.conflicts import refresh_booking_conflicts

    qs = Booking.objects.all().order_by("id").iterator(chunk_size=200)
    for booking in qs:
        snapshot = booking.conflict_snapshot or []
        if not any(
            isinstance(item, dict)
            and str(item.get("code") or "")
            in {"multi_port_proximity", "multi_port_conflict"}
            for item in snapshot
        ):
            continue
        refresh_booking_conflicts(booking)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0021_refresh_geo_proximity_conflicts"),
    ]

    operations = [
        migrations.RunPython(
            refresh_multi_port_conflict_snapshots,
            noop_reverse,
        ),
    ]
