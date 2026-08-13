"""Remove retired mooring_capacity avisos from persisted conflict snapshots."""

from django.db import migrations


def strip_mooring_capacity(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    rank = {"red": 3, "yellow": 2, "green": 1}
    to_update = []
    qs = Booking.objects.exclude(conflict_snapshot=[]).only(
        "id",
        "has_conflict",
        "conflict_severity",
        "conflict_snapshot",
    )
    for booking in qs.iterator(chunk_size=500):
        snap = booking.conflict_snapshot or []
        if not any(
            isinstance(item, dict) and item.get("code") == "mooring_capacity"
            for item in snap
        ):
            continue
        next_snap = [
            item
            for item in snap
            if not (isinstance(item, dict) and item.get("code") == "mooring_capacity")
        ]
        best = None
        best_n = 0
        for item in next_snap:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "")
            n = rank.get(sev, 0)
            if n > best_n:
                best_n = n
                best = sev
        active = [
            item
            for item in next_snap
            if isinstance(item, dict) and item.get("severity") in ("yellow", "red")
        ]
        booking.conflict_snapshot = next_snap
        booking.has_conflict = bool(active)
        booking.conflict_severity = best if active and best in {"yellow", "red", "green"} else None
        to_update.append(booking)
        if len(to_update) >= 500:
            Booking.objects.bulk_update(
                to_update,
                ["conflict_snapshot", "has_conflict", "conflict_severity"],
            )
            to_update = []
    if to_update:
        Booking.objects.bulk_update(
            to_update,
            ["conflict_snapshot", "has_conflict", "conflict_severity"],
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0017_booking_conflict_severity"),
    ]

    operations = [
        migrations.RunPython(strip_mooring_capacity, noop_reverse),
    ]
