from django.db import migrations, models


def backfill_conflict_severity(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    rank = {"red": 3, "yellow": 2, "green": 1}
    qs = Booking.objects.filter(has_conflict=True).only("id", "conflict_snapshot")
    to_update = []
    for booking in qs.iterator(chunk_size=500):
        best = None
        best_n = 0
        for item in booking.conflict_snapshot or []:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "")
            n = rank.get(sev, 0)
            if n > best_n:
                best_n = n
                best = sev
        if best in {"yellow", "red", "green"}:
            booking.conflict_severity = best
            to_update.append(booking)
        if len(to_update) >= 500:
            Booking.objects.bulk_update(to_update, ["conflict_severity"])
            to_update = []
    if to_update:
        Booking.objects.bulk_update(to_update, ["conflict_severity"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0016_refresh_loa_pair_conflicts"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="conflict_severity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("yellow", "Yellow"),
                    ("red", "Red"),
                    ("green", "Green"),
                ],
                db_index=True,
                help_text=(
                    "Highest severity in conflict_snapshot (yellow|red); "
                    "null when no conflict."
                ),
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_conflict_severity, noop_reverse),
    ]
