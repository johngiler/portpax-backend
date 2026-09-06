"""Backfill changed_fields / link counts on existing BookingRunBatch rows."""

from __future__ import annotations

from django.db import migrations


SKIP_CHANGE_KEYS = frozenset(
    {
        "source",
        "entity",
        "context",
        "run_batch_id",
        "import_batch_id",
        "acknowledge_combined_red",
    }
)


def _field_keys(changes: dict) -> list[str]:
    keys: list[str] = []
    for key, value in changes.items():
        if key in SKIP_CHANGE_KEYS:
            continue
        if isinstance(value, dict) and (
            "from" in value or "to" in value or "old" in value or "new" in value
        ):
            keys.append(key)
        elif key == "status":
            keys.append(key)
    return keys


def forwards(apps, schema_editor):
    BookingAuditEntry = apps.get_model("audit", "BookingAuditEntry")
    BookingRunBatch = apps.get_model("bookings", "BookingRunBatch")

    for batch in BookingRunBatch.objects.all().iterator():
        entries = list(
            BookingAuditEntry.objects.filter(changes__run_batch_id=batch.id)
        )
        if not entries:
            # Legacy LTA agreement batches created without field tracking.
            if batch.kind == "lta_agreement" and not (batch.changed_fields or []):
                batch.changed_fields = ["long_term_agreement"]
                meta = dict(batch.meta or {})
                if "linked" not in meta and "unlinked" not in meta:
                    # Best-effort: treat all as linked if unknown.
                    meta["linked"] = int(batch.success_count or 0)
                    meta["unlinked"] = 0
                batch.meta = meta
                batch.save(update_fields=["changed_fields", "meta"])
            continue

        fields: set[str] = set(batch.changed_fields or [])
        linked = 0
        unlinked = 0
        for entry in entries:
            changes = entry.changes if isinstance(entry.changes, dict) else {}
            fields.update(_field_keys(changes))
            if entry.action == "lta_linked":
                linked += 1
            elif entry.action == "lta_unlinked":
                unlinked += 1

        if batch.kind == "lta_agreement" and "long_term_agreement" not in fields:
            fields.add("long_term_agreement")

        meta = dict(batch.meta or {})
        if batch.kind == "lta_agreement":
            meta["linked"] = linked
            meta["unlinked"] = unlinked

        batch.changed_fields = sorted(fields)
        batch.meta = meta
        batch.save(update_fields=["changed_fields", "meta"])


def backwards(apps, schema_editor):
    # Leave enriched metadata in place.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0033_backfill_booking_run_batches"),
        ("audit", "0006_port_and_shipping_line_audit_entry"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
