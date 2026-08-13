from django.db import migrations


def refresh_conflicts_for_loa_pairs(apps, schema_editor):
    """Backfill has_conflict for bookings already assigned on LOA recalc pairs."""
    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
    from apps.bookings.models import Booking
    from apps.bookings.services.validation.conflicts import refresh_booking_conflicts
    from apps.catalogs.models import PositionLoaRecalcRule

    position_ids: set[int] = set()
    for rule in PositionLoaRecalcRule.objects.filter(is_active=True):
        position_ids.add(rule.position_a_id)
        position_ids.add(rule.position_b_id)
    if not position_ids:
        return

    qs = (
        Booking.objects.filter(
            position_id__in=position_ids,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        )
        .order_by("id")
        .iterator(chunk_size=200)
    )
    for booking in qs:
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
