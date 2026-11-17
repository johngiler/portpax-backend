from django.db import migrations


def _live_booking_schema_ready(schema_editor) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'bookings_booking'
              AND column_name = 'operation_notes'
            """
        )
        return cursor.fetchone() is not None


def refresh_geo_proximity_conflicts(apps, schema_editor):
    """Recompute conflict snapshots after PortProximity geo rule replaced ±days heuristic."""
    Booking = apps.get_model("bookings", "Booking")
    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES

    booking_ids = list(
        Booking.objects.filter(status__in=OCCUPATION_CONFLICT_STATUSES)
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not booking_ids or not _live_booking_schema_ready(schema_editor):
        return

    from apps.bookings.models import Booking as LiveBooking
    from apps.bookings.services.validation.conflicts import refresh_booking_conflicts

    for booking in (
        LiveBooking.objects.filter(id__in=booking_ids)
        .order_by("id")
        .iterator(chunk_size=200)
    ):
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
