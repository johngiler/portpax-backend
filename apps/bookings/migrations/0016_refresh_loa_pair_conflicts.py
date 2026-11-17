from django.db import migrations


def refresh_conflicts_for_loa_pairs(apps, schema_editor):
    """Backfill has_conflict for bookings already assigned on LOA recalc pairs."""
    Booking = apps.get_model("bookings", "Booking")
    PositionLoaRecalcRule = apps.get_model("catalogs", "PositionLoaRecalcRule")

    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES

    position_ids: set[int] = set()
    for rule in PositionLoaRecalcRule.objects.filter(is_active=True):
        if rule.position_a_id:
            position_ids.add(rule.position_a_id)
        if rule.position_b_id:
            position_ids.add(rule.position_b_id)
    if not position_ids:
        return

    # Historical model only — never SELECT the live Booking row set here.
    # Live Booking includes columns added after this migration (e.g. operation_notes).
    booking_ids = list(
        Booking.objects.filter(
            position_id__in=position_ids,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not booking_ids:
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'bookings_booking'
              AND column_name = 'operation_notes'
            """
        )
        if cursor.fetchone() is None:
            # Fresh migrate: schema not at live model yet; nothing safe to refresh.
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
        ("bookings", "0015_booking_has_conflict"),
        ("catalogs", "0037_alter_position_min_loa_m"),
    ]

    operations = [
        migrations.RunPython(refresh_conflicts_for_loa_pairs, noop_reverse),
    ]
