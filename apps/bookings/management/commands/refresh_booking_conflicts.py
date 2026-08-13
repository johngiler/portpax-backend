"""Recompute and persist has_conflict + conflict_snapshot on bookings."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
from apps.bookings.models import Booking
from apps.bookings.services.validation.conflicts import refresh_booking_conflicts


class Command(BaseCommand):
    help = (
        "Refresh has_conflict / conflict_snapshot for bookings "
        "(operational conflicts for list, calendar, and availability)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Limit to bookings at this port id.",
        )
        parser.add_argument(
            "--call-date",
            type=str,
            default=None,
            help="Limit to a single call_date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--only-stale",
            action="store_true",
            help="Only rows currently flagged has_conflict=False with a position.",
        )

    def handle(self, *args, **options):
        qs = Booking.objects.filter(
            status__in=OCCUPATION_CONFLICT_STATUSES,
        ).exclude(position_id=None).order_by("id")
        if options["port"]:
            qs = qs.filter(port_id=options["port"])
        if options["call_date"]:
            qs = qs.filter(call_date=options["call_date"])
        if options["only_stale"]:
            qs = qs.filter(has_conflict=False)

        total = qs.count()
        flagged = 0
        cleared = 0
        unchanged = 0
        self.stdout.write(f"Refreshing {total} booking(s)…")

        for i, booking in enumerate(qs.iterator(chunk_size=200), start=1):
            prev = bool(booking.has_conflict)
            refresh_booking_conflicts(booking)
            booking.refresh_from_db(fields=["has_conflict"])
            now = bool(booking.has_conflict)
            if now and not prev:
                flagged += 1
            elif prev and not now:
                cleared += 1
            else:
                unchanged += 1
            if i % 500 == 0 or i == total:
                self.stdout.write(f"  …{i}/{total}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. newly_flagged={flagged} cleared={cleared} unchanged={unchanged}"
            )
        )
