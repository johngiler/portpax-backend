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


def refresh_multi_port_conflict_snapshots(apps, schema_editor):
    """Rebuild proximity conflict messages with geo formula detail."""
    Booking = apps.get_model("bookings", "Booking")

    booking_ids = list(
        Booking.objects.exclude(conflict_snapshot=[])
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
