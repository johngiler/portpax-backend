"""Drop LTA horizon/slot conflicts on ports with no active LTA agreements."""

from django.db import migrations

LTA_WINDOW_CODES = frozenset(
    {
        "lta_horizon_denied",
        "lta_beyond_horizon",
        "lta_slot_reserved",
    }
)


def strip_lta_on_ports_without_agreements(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    LongTermAgreement = apps.get_model("bookings", "LongTermAgreement")
    rank = {"red": 3, "yellow": 2, "green": 1}

    ports_with_lta = set(
        LongTermAgreement.objects.filter(is_active=True).values_list(
            "port_id", flat=True
        )
    )

    to_update = []
    qs = (
        Booking.objects.exclude(conflict_snapshot=[])
        .exclude(port_id__in=ports_with_lta)
        .only("id", "has_conflict", "conflict_severity", "conflict_snapshot")
    )
    for booking in qs.iterator(chunk_size=500):
        snap = booking.conflict_snapshot or []
        if not any(
            isinstance(item, dict) and item.get("code") in LTA_WINDOW_CODES
            for item in snap
        ):
            continue
        next_snap = [
            item
            for item in snap
            if not (
                isinstance(item, dict) and item.get("code") in LTA_WINDOW_CODES
            )
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
        booking.conflict_severity = (
            best if active and best in {"yellow", "red", "green"} else None
        )
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
        ("bookings", "0019_draft_conflict_position_only"),
    ]

    operations = [
        migrations.RunPython(strip_lta_on_ports_without_agreements, noop_reverse),
    ]
