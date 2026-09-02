"""Re-run future planned_pax backfill including call_date == today.

0029 used call_date__gt=as_of, so same-day futures kept capacity.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from apps.bookings.services.booking.planned_pax import (
        recompute_future_planned_pax_from_history,
    )

    recompute_future_planned_pax_from_history()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0029_backfill_future_planned_pax_avg"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
