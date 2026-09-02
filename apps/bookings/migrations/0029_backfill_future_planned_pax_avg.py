"""Backfill future bookings planned_pax from vessel actual_pax average."""

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
        ("bookings", "0028_recompute_real_planned_pax_avg"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
