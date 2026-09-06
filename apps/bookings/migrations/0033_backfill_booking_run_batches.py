"""One-time backfill: group historical mass/LTA audits into BookingRunBatch cards."""

from __future__ import annotations

from datetime import timedelta

from django.db import migrations

# Audits in the same process are usually consecutive; allow headroom for large LTA jobs.
CLUSTER_WINDOW = timedelta(seconds=120)

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


def _source_of(changes: dict) -> str | None:
    raw = changes.get("source")
    return raw if isinstance(raw, str) else None


def _agreement_code(changes: dict) -> str | None:
    block = changes.get("long_term_agreement")
    if isinstance(block, dict):
        for key in ("new", "to", "old", "from"):
            val = block.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    code = changes.get("agreement_code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _kind_for_entry(action: str, changes: dict) -> str | None:
    source = _source_of(changes)
    if source == "bulk_edit":
        return "mass_update"
    if source == "lta_generate":
        return "lta_generate"
    if source == "lta_agreement" or action in ("lta_linked", "lta_unlinked"):
        return "lta_agreement"
    return None


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


def _stamp_run_batch_id(BookingAuditEntry, entry_ids: list[int], batch_id: int) -> None:
    for entry in BookingAuditEntry.objects.filter(id__in=entry_ids).iterator():
        changes = dict(entry.changes or {})
        if changes.get("run_batch_id") == batch_id:
            continue
        changes["run_batch_id"] = batch_id
        if "source" not in changes:
            kind = _kind_for_entry(entry.action, changes)
            if kind == "mass_update":
                changes["source"] = "bulk_edit"
            elif kind == "lta_generate":
                changes["source"] = "lta_generate"
            elif kind == "lta_agreement":
                changes["source"] = "lta_agreement"
        entry.changes = changes
        entry.save(update_fields=["changes"])


def forwards(apps, schema_editor):
    BookingAuditEntry = apps.get_model("audit", "BookingAuditEntry")
    BookingRunBatch = apps.get_model("bookings", "BookingRunBatch")

    candidates = (
        BookingAuditEntry.objects.exclude(changes__has_key="run_batch_id")
        .order_by("created_at", "id")
        .iterator(chunk_size=500)
    )

    clusters: list[dict] = []

    for entry in candidates:
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        kind = _kind_for_entry(entry.action, changes)
        if kind is None:
            continue
        agreement = _agreement_code(changes) if kind != "mass_update" else None
        user_id = entry.user_id
        created_at = entry.created_at

        matched = None
        for cluster in reversed(clusters[-40:]):
            if cluster["kind"] != kind:
                continue
            if cluster["user_id"] != user_id:
                continue
            if cluster["agreement"] != agreement:
                continue
            if created_at - cluster["last_at"] > CLUSTER_WINDOW:
                continue
            matched = cluster
            break

        if matched is None:
            matched = {
                "kind": kind,
                "user_id": user_id,
                "agreement": agreement,
                "entries": [],
                "first_at": created_at,
                "last_at": created_at,
            }
            clusters.append(matched)

        matched["entries"].append(entry)
        matched["last_at"] = created_at

    for cluster in clusters:
        entries = cluster["entries"]
        if not entries:
            continue

        booking_ids: list[int] = []
        seen: set[int] = set()
        changed: set[str] = set()
        for entry in entries:
            if entry.booking_id and entry.booking_id not in seen:
                seen.add(entry.booking_id)
                booking_ids.append(entry.booking_id)
            changed.update(
                _field_keys(entry.changes if isinstance(entry.changes, dict) else {})
            )

        kind = cluster["kind"]
        agreement = cluster["agreement"]
        if kind == "mass_update":
            label = "Actualización masiva"
        elif kind == "lta_generate":
            label = f"Creación LTA · {agreement}" if agreement else "Creación LTA"
        else:
            label = (
                f"Actualización LTA · {agreement}" if agreement else "Actualización LTA"
            )

        batch = BookingRunBatch.objects.create(
            kind=kind,
            created_by_id=cluster["user_id"],
            label=label,
            booking_ids=booking_ids,
            success_count=len(booking_ids),
            failed_count=0,
            changed_fields=sorted(changed) if kind == "mass_update" else [],
            failures=[],
            meta={
                "backfilled": True,
                "agreement_code": agreement,
                "entry_count": len(entries),
                "first_audit_at": cluster["first_at"].isoformat(),
                "last_audit_at": cluster["last_at"].isoformat(),
            },
        )
        BookingRunBatch.objects.filter(pk=batch.pk).update(
            created_at=cluster["first_at"],
        )
        _stamp_run_batch_id(
            BookingAuditEntry,
            [e.id for e in entries],
            batch.pk,
        )


def backwards(apps, schema_editor):
    from apps.audit.services.deletion import allow_audit_deletion

    BookingAuditEntry = apps.get_model("audit", "BookingAuditEntry")
    BookingRunBatch = apps.get_model("bookings", "BookingRunBatch")

    batches = list(
        BookingRunBatch.objects.filter(meta__backfilled=True).values_list(
            "id", flat=True
        )
    )
    if not batches:
        return

    for entry in BookingAuditEntry.objects.filter(
        changes__run_batch_id__in=batches
    ).iterator(chunk_size=500):
        changes = dict(entry.changes or {})
        batch_id = changes.get("run_batch_id")
        if batch_id not in batches:
            continue
        changes.pop("run_batch_id", None)
        entry.changes = changes
        entry.save(update_fields=["changes"])

    with allow_audit_deletion():
        BookingRunBatch.objects.filter(id__in=batches).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0032_booking_tags_and_run_batches"),
        ("audit", "0006_port_and_shipping_line_audit_entry"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
