"""Recompute and persist has_conflict + conflict_snapshot on bookings."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
from apps.bookings.models import Booking
from apps.bookings.services.validation.conflicts import (
    refresh_booking_conflicts,
    refresh_booking_conflicts_for_vessel_itinerary,
)


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
            "--vessel",
            type=int,
            default=None,
            help="Limit to bookings for this vessel id (full itinerary refresh).",
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
            help="Only rows currently flagged has_conflict=False.",
        )
        parser.add_argument(
            "--assigned-only",
            action="store_true",
            help=(
                "Skip bookings without position (legacy pier-only refill). "
                "Geo proximity applies to all active bookings."
            ),
        )

    def handle(self, *args, **options):
        if options["vessel"]:
            total = refresh_booking_conflicts_for_vessel_itinerary(
                options["vessel"],
                notify=True,
                notify_updates=False,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. refreshed_itinerary vessel_id={options['vessel']} count={total}"
                )
            )
            return

        qs = Booking.objects.filter(
            status__in=OCCUPATION_CONFLICT_STATUSES,
        ).order_by("id")
        if options["assigned_only"]:
            qs = qs.exclude(position_id=None)
        if options["port"]:
            qs = qs.filter(port_id=options["port"])
        if options["call_date"]:
            qs = qs.filter(call_date=options["call_date"])
        if options["only_stale"]:
            qs = qs.filter(has_conflict=False)

        total = qs.count()
        flagged = 0
        cleared = 0
        snapshot_updated = 0
        unchanged = 0
        self.stdout.write(f"Refreshing {total} booking(s)…")

        for i, booking in enumerate(qs.iterator(chunk_size=200), start=1):
            prev = bool(booking.has_conflict)
            prev_codes = {
                str(item.get("code") or "")
                for item in (booking.conflict_snapshot or [])
            }
            prev_severity = booking.conflict_severity or None
            refresh_booking_conflicts(booking, notify=True, notify_updates=False)
            booking.refresh_from_db(
                fields=["has_conflict", "conflict_severity", "conflict_snapshot"]
            )
            now = bool(booking.has_conflict)
            next_codes = {
                str(item.get("code") or "")
                for item in (booking.conflict_snapshot or [])
            }
            next_severity = booking.conflict_severity or None
            if now and not prev:
                flagged += 1
            elif prev and not now:
                cleared += 1
            elif prev_codes != next_codes or prev_severity != next_severity:
                snapshot_updated += 1
            else:
                unchanged += 1
            if i % 500 == 0 or i == total:
                self.stdout.write(f"  …{i}/{total}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. newly_flagged={flagged} cleared={cleared} "
                f"snapshot_updated={snapshot_updated} unchanged={unchanged}"
            )
        )
