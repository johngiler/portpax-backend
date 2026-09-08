"""Re-purge conflict notification spam after a post-0002 refresh on DEV.

Migration 0002 cleared the first flood; a later ``refresh_booking_conflicts``
recreated conflict_detected / conflict_resolved rows. Same cutoff: keep
legitimate notifications from before the original geo-window mistake.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.db import migrations

# Same cutoff as 0002 — just before the first flood (~23:29 UTC).
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
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_purge_geo_window_conflict_notification_spam"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
