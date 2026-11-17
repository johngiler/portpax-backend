from django.db import migrations
from django.db.models import Q


def delete_zombie_import_batches(apps, schema_editor):
    """Remove crash leftovers: 0 created / 0 failed / no retry payload."""
    BookingImportBatch = apps.get_model("bookings", "BookingImportBatch")
    from apps.audit.services.deletion import allow_audit_deletion

    zombies = BookingImportBatch.objects.filter(
        created_count=0,
        failed_count=0,
    ).filter(Q(retry_rows=[]) | Q(retry_rows__isnull=True))

    with allow_audit_deletion():
        zombies.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0040_booking_cancellation_notes"),
    ]

    operations = [
        migrations.RunPython(delete_zombie_import_batches, noop_reverse),
    ]
