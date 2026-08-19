from django.db import migrations


def refresh_geo_proximity_conflicts(apps, schema_editor):
    """Recompute conflict snapshots after PortProximity geo rule replaced ±days heuristic."""
    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
    from apps.bookings.models import Booking
    from apps.bookings.services.validation.conflicts import refresh_booking_conflicts

    qs = (
        Booking.objects.filter(status__in=OCCUPATION_CONFLICT_STATUSES)
        .order_by("id")
        .iterator(chunk_size=200)
    )
    for booking in qs:
        refresh_booking_conflicts(booking)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0020_lta_conflicts_require_port_agreement"),
        ("catalogs", "0040_alter_portproximity_speed_knots_used"),
    ]

    operations = [
        migrations.RunPython(refresh_geo_proximity_conflicts, noop_reverse),
    ]
