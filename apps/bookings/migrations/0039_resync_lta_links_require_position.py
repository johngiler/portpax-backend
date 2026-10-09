"""Re-sync LTA booking links after sticky-keep ignored pier moves."""

from django.db import migrations


def resync_all_lta_links(apps, schema_editor):
    """
    Apply set-diff rematch for every agreement so CL/CO bookings on the wrong
    pier are unlinked and reattached to the best matching agreement.
    """
    from apps.bookings.models import LongTermAgreement
    from apps.bookings.services.lta.link_bookings import resync_agreement_bookings

    for agreement in (
        LongTermAgreement.objects.all()
        .order_by("id")
        .prefetch_related("positions", "vessels")
        .iterator(chunk_size=50)
    ):
        resync_agreement_bookings(agreement, dry_run=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0038_cancellation_reason_lta_claimed"),
    ]

    operations = [
        migrations.RunPython(resync_all_lta_links, noop_reverse),
    ]
