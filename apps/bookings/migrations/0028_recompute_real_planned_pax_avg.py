"""Recompute Real planned_pax from chronological actual_pax averages."""

from django.db import migrations


def forwards(apps, schema_editor):
    # Historical models lack service helpers; use live ORM for data repair.
    from apps.bookings.services.booking.planned_pax import (
        recompute_real_planned_pax_chronological,
    )

    recompute_real_planned_pax_chronological()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0027_backfill_real_planned_pax"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
