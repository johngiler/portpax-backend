"""Backfill long_term_agreement FK on bookings that match active LTAs.

The agreements list ``linked_bookings_count`` is a live Count annotation — it
updates automatically once bookings have the FK. Use this command after
importing historical bookings or creating LTAs late.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.bookings.models import LongTermAgreement
from apps.bookings.services.lta.link_bookings import link_matching_bookings


class Command(BaseCommand):
    help = (
        "Assign matching bookings to LTA agreements (FK backfill). "
        "Does not change booking status. Count in the LTA list refreshes from the FK."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--code",
            type=str,
            default=None,
            help="Only this agreement code (e.g. msc-pop-grandiosa-wed).",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Limit to agreements for this port id.",
        )
        parser.add_argument(
            "--shipping-line",
            type=int,
            default=None,
            help="Limit to agreements for this shipping line id.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also process inactive agreements (default: active only).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matches without writing or auditing.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        qs = LongTermAgreement.objects.select_related("port", "shipping_line").order_by(
            "code"
        )
        if not options["include_inactive"]:
            qs = qs.filter(is_active=True)
        if options["code"]:
            qs = qs.filter(code=options["code"].strip())
        if options["port"]:
            qs = qs.filter(port_id=options["port"])
        if options["shipping_line"]:
            qs = qs.filter(shipping_line_id=options["shipping_line"])

        agreements = list(qs)
        if options["code"] and not agreements:
            raise CommandError(f"No LTA found with code={options['code']!r}.")

        if not agreements:
            self.stdout.write(self.style.WARNING("No agreements to process."))
            return

        mode = "DRY-RUN" if dry_run else "WRITE"
        self.stdout.write(f"[{mode}] Processing {len(agreements)} agreement(s)…")

        total_linked = 0
        total_skipped = 0
        for agreement in agreements:
            result = link_matching_bookings(agreement, dry_run=dry_run)
            linked = int(result.get("linked") or 0)
            skipped = int(result.get("skipped") or 0)
            total_linked += linked
            total_skipped += skipped
            detail = result.get("detail")
            if detail and linked == 0:
                self.stdout.write(f"  {agreement.code}: {detail}")
            else:
                self.stdout.write(
                    f"  {agreement.code}: linked={linked} skipped={skipped}"
                )

        # Live counts after write (or current counts on dry-run).
        counts = (
            LongTermAgreement.objects.filter(id__in=[a.id for a in agreements])
            .annotate(linked_bookings_count=Count("bookings", distinct=True))
            .order_by("code")
            .values_list("code", "linked_bookings_count")
        )
        self.stdout.write("")
        self.stdout.write("Current linked_bookings_count:")
        for code, count in counts:
            self.stdout.write(f"  {code}: {count}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done [{mode}]. agreements={len(agreements)} "
                f"linked={total_linked} skipped={total_skipped}"
            )
        )
