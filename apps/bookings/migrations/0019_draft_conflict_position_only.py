"""Recompute draft_too_deep using position min_draft_m only."""

from decimal import Decimal, InvalidOperation

from django.db import migrations


def _dec(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def refresh_draft_snapshots(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    Vessel = apps.get_model("catalogs", "Vessel")
    Position = apps.get_model("catalogs", "Position")
    rank = {"red": 3, "yellow": 2, "green": 1}

    vessel_draft = {
        row["id"]: _dec(row["draft_m"])
        for row in Vessel.objects.values("id", "draft_m")
    }
    position_depth = {
        row["id"]: (_dec(row["min_draft_m"]), row["code"])
        for row in Position.objects.values("id", "min_draft_m", "code")
    }

    to_update = []
    qs = Booking.objects.exclude(conflict_snapshot=[]).only(
        "id",
        "vessel_id",
        "position_id",
        "has_conflict",
        "conflict_severity",
        "conflict_snapshot",
    )
    for booking in qs.iterator(chunk_size=500):
        snap = list(booking.conflict_snapshot or [])
        had_draft = any(
            isinstance(item, dict) and item.get("code") == "draft_too_deep"
            for item in snap
        )
        without_draft = [
            item
            for item in snap
            if not (isinstance(item, dict) and item.get("code") == "draft_too_deep")
        ]

        draft_issue = None
        depth_info = position_depth.get(booking.position_id) if booking.position_id else None
        draft = vessel_draft.get(booking.vessel_id)
        if depth_info is not None and draft is not None:
            depth, code = depth_info
            if depth is not None and draft > depth:
                draft_issue = {
                    "code": "draft_too_deep",
                    "message": (
                        f"Calado del barco ({draft} m) supera la profundidad disponible "
                        f"({depth} m) en {code}."
                    ),
                    "severity": "red",
                    "level": "warning",
                }

        if draft_issue is None and not had_draft:
            continue

        next_snap = [*without_draft, draft_issue] if draft_issue else without_draft
        if next_snap == snap:
            continue

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
        ("bookings", "0018_drop_mooring_capacity_conflicts"),
    ]

    operations = [
        migrations.RunPython(refresh_draft_snapshots, noop_reverse),
    ]
