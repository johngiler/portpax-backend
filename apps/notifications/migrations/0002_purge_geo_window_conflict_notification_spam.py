"""Purge conflict notification spam from the widened geo-window refresh.

On 2026-09-07 an accidental MAX_GEO_PROXIMITY_WINDOW_DAYS=14 refresh flooded
campanita with conflict_detected / conflict_resolved rows. Keep all other
notifications and any conflict alerts created before that flood.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.db import migrations

# Just before the first flood batch (~23:29 UTC = 18:29 local UTC-5).
SPAM_CUTOFF = datetime(2026, 9, 7, 23, 25, 0, tzinfo=timezone.utc)

CONFLICT_EVENTS = (
    "conflict_detected",
    "conflict_resolved",
    "conflict_updated",
)


def forwards(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    Notification.objects.filter(
        event__in=CONFLICT_EVENTS,
        created_at__gte=SPAM_CUTOFF,
    ).delete()


def backwards(apps, schema_editor):
    # Deleted rows cannot be restored.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
