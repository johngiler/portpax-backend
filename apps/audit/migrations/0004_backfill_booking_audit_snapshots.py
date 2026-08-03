from django.db import migrations


def backfill_booking_audit_snapshots(apps, schema_editor):
    BookingAuditEntry = apps.get_model("audit", "BookingAuditEntry")
    for entry in BookingAuditEntry.objects.filter(booking_id__isnull=False).iterator():
        booking = entry.booking
        if booking is None:
            continue
        update_fields = []
        if not entry.booking_code:
            entry.booking_code = booking.booking_code or ""
            update_fields.append("booking_code")
        if entry.port_id is None and booking.port_id is not None:
            entry.port_id = booking.port_id
            update_fields.append("port_id")
        if update_fields:
            entry.save(update_fields=update_fields)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0003_booking_audit_immutable_snapshots"),
    ]

    operations = [
        migrations.RunPython(backfill_booking_audit_snapshots, noop_reverse),
    ]
