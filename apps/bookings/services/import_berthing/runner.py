"""Upsert Booking rows from parsed berthing JSON."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.confirmation_pdf import generate_confirmation_pdfs
from apps.bookings.services.import_berthing.match import (
    MatchStats,
    resolve_port,
    resolve_position,
    resolve_shipping_line,
    resolve_vessel,
)
from apps.bookings.services.import_berthing.parse import parse_berthing_folder


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def load_rows_from_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("rows", [])
    return data


def write_parsed_json(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(rows),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_berthing_rows(
    rows: list[dict[str, Any]],
    *,
    delete_data: bool = False,
    dry_run: bool = False,
    generate_confirmations: bool = True,
    force_confirmation: bool = False,
) -> dict[str, Any]:
    stats = MatchStats()
    created = 0
    updated = 0
    invalid: list[dict[str, Any]] = []
    existing_codes = set(Booking.objects.values_list("booking_code", flat=True))

    def process() -> None:
        nonlocal created, updated, existing_codes
        if delete_data:
            Booking.objects.all().delete()
            existing_codes = set()

        for row in rows:
            call_date = row.get("call_date")
            ship = row.get("ship")
            status = row.get("status")
            if not call_date or not ship:
                invalid.append({**row, "reason": "missing_call_date_or_ship"})
                continue
            if not status or status not in BookingStatus.values:
                invalid.append({**row, "reason": f"unknown_status:{row.get('status_raw')}"} )
                continue

            port = resolve_port(row["port_key"])
            line = resolve_shipping_line(row.get("brand"), row.get("corp"), stats)
            vessel = resolve_vessel(ship, line, stats)
            position = resolve_position(port, row.get("berth_assign"), stats)
            eta = _parse_time(row.get("eta"))
            etd = _parse_time(row.get("etd"))
            pax = row.get("pax")

            planned_pax = None
            actual_pax = None
            if isinstance(pax, int):
                if status == BookingStatus.R:
                    actual_pax = pax
                else:
                    planned_pax = pax

            defaults = {
                "shipping_line": line,
                "position": position,
                "eta": eta,
                "etd": etd,
                "status": status,
                "planned_pax": planned_pax,
                "actual_pax": actual_pax,
                "notes": "Imported from BERTHING PAPERS",
            }

            existing = Booking.objects.filter(
                port=port,
                vessel=vessel,
                call_date=call_date,
            ).first()

            if existing:
                for key, value in defaults.items():
                    setattr(existing, key, value)
                existing.save()
                updated += 1
            else:
                code = resolve_unique_booking_code(
                    port,
                    line,
                    vessel,
                    datetime.strptime(call_date, "%Y-%m-%d").date(),
                    existing_codes,
                )
                existing_codes.add(code)
                Booking.objects.create(
                    port=port,
                    vessel=vessel,
                    call_date=call_date,
                    booking_code=code,
                    **defaults,
                )
                created += 1

    if dry_run:
        # Resolve matches without writing bookings / catalog creates still happen
        # unless we skip — for dry-run, only validate parse + match without DB writes.
        for row in rows:
            if not row.get("call_date") or not row.get("ship"):
                invalid.append({**row, "reason": "missing_call_date_or_ship"})
                continue
            if not row.get("status") or row["status"] not in BookingStatus.values:
                invalid.append({**row, "reason": f"unknown_status:{row.get('status_raw')}"})
                continue
        return {
            "dry_run": True,
            "parsed": len(rows),
            "valid": len(rows) - len(invalid),
            "invalid": len(invalid),
            "invalid_rows": invalid[:200],
            "would_delete": delete_data,
        }

    with transaction.atomic():
        process()

    confirmation_report: dict[str, Any] = {
        "generated": 0,
        "error_count": 0,
        "errors": [],
        "skipped": True,
    }
    if generate_confirmations:
        confirmation_report = generate_confirmation_pdfs(
            only_missing=not force_confirmation,
        )
        confirmation_report["skipped"] = False

    return {
        "parsed": len(rows),
        "created": created,
        "updated": updated,
        "invalid": len(invalid),
        "invalid_rows": invalid[:500],
        "lines_created": stats.lines_created,
        "vessels_created": stats.vessels_created,
        "positions_null": stats.positions_null,
        "created_lines": stats.created_lines[:200],
        "created_vessels": stats.created_vessels[:200],
        "deleted_before": delete_data,
        "confirmations": confirmation_report,
    }


def parse_and_write_json(xlsx_folder: Path, json_path: Path) -> list[dict[str, Any]]:
    rows = parse_berthing_folder(xlsx_folder)
    write_parsed_json(rows, json_path)
    return rows
