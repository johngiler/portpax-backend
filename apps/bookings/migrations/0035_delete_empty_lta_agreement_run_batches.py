"""Delete LTA agreement run batches with no net vínculo change (0/0/0).

Cards that only recorded unlink+relink churn (same agreement) are removed
together with their BookingAuditEntry rows stamped with that run_batch_id.
"""

from __future__ import annotations

from django.db import migrations

LTA_FIELDS = frozenset({"long_term_agreement", "long_term_agreement_id"})
SKIP_KEYS = frozenset(
    {
        "source",
        "entity",
        "context",
        "run_batch_id",
        "import_batch_id",
        "acknowledge_combined_red",
    }
)


def _side(value: object) -> object:
    if isinstance(value, dict):
        if "from" in value or "to" in value:
            return value.get("from"), value.get("to")
        if "old" in value or "new" in value:
            return value.get("old"), value.get("new")
    return None


def _field_sides(changes: dict) -> list[tuple[str, object, object]]:
    rows: list[tuple[str, object, object]] = []
    for key, value in changes.items():
        if key in SKIP_KEYS:
            continue
        sides = _side(value)
        if sides is None:
            continue
        rows.append((key, sides[0], sides[1]))
    return rows


def _has_net_booking_changes(entries) -> bool:
    """True if any booking keeps a net from→to after collapsing audits."""
    chains: dict[int, dict[str, list[tuple[object, object]]]] = {}
    for entry in entries:
        booking_id = entry.booking_id
        if booking_id is None:
            continue
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        by_field = chains.setdefault(booking_id, {})
        for field, fr, to in _field_sides(changes):
            by_field.setdefault(field, []).append((fr, to))

    for fields in chains.values():
        for sides in fields.values():
            if not sides:
                continue
            if sides[0][0] != sides[-1][1]:
                return True
    return False


def forwards(apps, schema_editor):
    from apps.audit.services.deletion import allow_audit_deletion

    BookingAuditEntry = apps.get_model("audit", "BookingAuditEntry")
    BookingRunBatch = apps.get_model("bookings", "BookingRunBatch")

    empty_ids: list[int] = []
    for batch in BookingRunBatch.objects.filter(
        kind="lta_agreement",
        failed_count=0,
    ).iterator():
        entries = list(
            BookingAuditEntry.objects.filter(changes__run_batch_id=batch.id)
        )
        if _has_net_booking_changes(entries):
            continue
        empty_ids.append(batch.id)

    if not empty_ids:
        return

    with allow_audit_deletion():
        BookingAuditEntry.objects.filter(
            changes__run_batch_id__in=empty_ids
        ).delete()
        BookingRunBatch.objects.filter(id__in=empty_ids).delete()


def backwards(apps, schema_editor):
    # Deleted empty churn batches cannot be restored.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0034_enrich_run_batch_changed_fields"),
        ("audit", "0006_port_and_shipping_line_audit_entry"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
