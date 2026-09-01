"""Upsert Booking rows from parsed berthing JSON (catalog match-only)."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingImportBatch, BookingStatus
from apps.bookings.services.booking.code import resolve_unique_booking_code
from apps.bookings.services.confirmation_pdf import generate_confirmation_pdfs
from apps.bookings.services.import_berthing.match import (
    resolve_port,
    resolve_position,
    resolve_shipping_line,
    resolve_vessel,
)
from apps.bookings.services.import_berthing.parse import parse_berthing_source
from apps.catalogs.models import Port

BERTHING_IMPORT_SOURCE = "berthing_import"
BERTHING_BATCH_LABEL_PREFIX = "BERTHING PAPERS"


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def _failure_reason_label(reason: str) -> str:
    labels = {
        "missing_call_date_or_ship": "Falta fecha de escala o barco",
        "unknown_status": "Estado de reserva no reconocido",
        "unknown_port_key": "Puerto no reconocido en el archivo",
        "port_not_found": "Puerto no encontrado en catálogo",
        "shipping_line_not_found": "Naviera no encontrada en catálogo",
        "vessel_not_found": "Barco no encontrado en catálogo",
        "position_not_found": "Posición no encontrada en catálogo",
        "unmatched": "Sin match en catálogo",
    }
    return labels.get(reason, reason)


def _failure_row(row: dict[str, Any], *, reason: str, detail: str = "") -> dict[str, Any]:
    issue = _failure_reason_label(reason)
    if detail:
        issue = f"{issue} ({detail})"
    row_number = row.get("row_number") or row.get("source_row")
    return {
        "id": f"berthing-{row_number or '?'}-{reason}",
        "row_number": row_number,
        "source_file": row.get("source_file"),
        "source_row": row.get("source_row"),
        "call_date": row.get("call_date"),
        "ship": row.get("ship"),
        "vessel_name": row.get("ship"),
        "port_raw": row.get("port_key"),
        "port_key": row.get("port_key"),
        "brand": row.get("brand"),
        "corp": row.get("corp"),
        "berth_assign": row.get("berth_assign"),
        "status_raw": row.get("status_raw"),
        "reason": reason,
        "detail": detail,
        "issues": [issue],
        "selectable": False,
    }


def _resolve_row_catalog(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str]:
    try:
        port = resolve_port(row["port_key"])
    except KeyError:
        return None, "unknown_port_key", f"port_key={row.get('port_key')!r}"
    except Port.DoesNotExist:
        return None, "port_not_found", f"port_key={row.get('port_key')!r}"

    line = resolve_shipping_line(row.get("brand"), row.get("corp"))
    if line is None:
        brand = row.get("brand") or ""
        corp = row.get("corp") or ""
        return (
            None,
            "shipping_line_not_found",
            f"brand={brand!r} corp={corp!r}",
        )

    ship = row.get("ship") or ""
    vessel = resolve_vessel(
        ship,
        line,
        loa_m=row.get("loa_m"),
        brand=row.get("brand"),
        corp=row.get("corp"),
    )
    if vessel is None:
        return (
            None,
            "vessel_not_found",
            f"ship={ship!r} line={line.code}",
        )

    berth_assign = row.get("berth_assign")
    position = resolve_position(port, berth_assign)
    if berth_assign and position is None:
        return (
            None,
            "position_not_found",
            f"berth_assign={berth_assign!r} port={port.code}",
        )

    return (
        {
            "port": port,
            "line": line,
            "vessel": vessel,
            "position": position,
        },
        None,
        "",
    )


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


def _persist_batch(
    *,
    batch: BookingImportBatch,
    created_count: int,
    updated_count: int,
    failures: list[dict[str, Any]],
    created_booking_ids: list[int],
) -> BookingImportBatch:
    failed_count = len(failures)
    batch.label = (
        f"{BERTHING_BATCH_LABEL_PREFIX} · "
        f"{created_count} creadas, {updated_count} actualizadas, {failed_count} fallidas"
    )
    batch.created_count = created_count
    batch.failed_count = failed_count
    batch.created_booking_ids = created_booking_ids
    batch.failures = failures[:500]
    batch.retry_rows = failures[:500]
    batch.finished_at = timezone.now()
    batch.save(
        update_fields=[
            "label",
            "created_count",
            "failed_count",
            "created_booking_ids",
            "failures",
            "retry_rows",
            "finished_at",
            "status",
        ]
    )
    return batch


def import_berthing_rows(
    rows: list[dict[str, Any]],
    *,
    delete_data: bool = False,
    dry_run: bool = False,
    generate_confirmations: bool = True,
    force_confirmation: bool = False,
    created_by=None,
) -> dict[str, Any]:
    created = 0
    updated = 0
    invalid: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    pax_delta_warnings: list[dict[str, Any]] = []
    created_booking_ids: list[int] = []
    existing_codes = set(Booking.objects.values_list("booking_code", flat=True))
    batch_id: int | None = None

    def process() -> None:
        nonlocal created, updated, existing_codes, batch_id
        if delete_data:
            Booking.objects.all().delete()
            existing_codes = set()

        batch = BookingImportBatch.objects.create(
            created_by=created_by,
            source=BookingImportBatch.Source.FILE,
            label=f"{BERTHING_BATCH_LABEL_PREFIX} · importación",
            requested_count=len(rows),
            status=BookingImportBatch.Status.COMPLETED,
        )
        batch_id = batch.id
        audit_changes = {
            "source": BERTHING_IMPORT_SOURCE,
            "import_batch_id": batch.id,
        }

        for row in rows:
            call_date = row.get("call_date")
            ship = row.get("ship")
            status = row.get("status")
            if not call_date or not ship:
                invalid.append(_failure_row(row, reason="missing_call_date_or_ship"))
                continue
            if not status or status not in BookingStatus.values:
                invalid.append(
                    _failure_row(
                        row,
                        reason="unknown_status",
                        detail=str(row.get("status_raw")),
                    )
                )
                continue

            resolved, fail_reason, fail_detail = _resolve_row_catalog(row)
            if resolved is None:
                unmatched.append(
                    _failure_row(row, reason=fail_reason or "unmatched", detail=fail_detail)
                )
                continue

            port = resolved["port"]
            line = resolved["line"]
            vessel = resolved["vessel"]
            position = resolved["position"]
            eta = _parse_time(row.get("eta"))
            etd = _parse_time(row.get("etd"))
            eta_real = _parse_time(row.get("eta_real"))
            etd_real = _parse_time(row.get("etd_real"))
            pax = row.get("pax")
            pax_delta = row.get("pax_real_delta")

            planned_pax = None
            actual_pax = None
            if status == BookingStatus.R:
                if isinstance(pax_delta, int):
                    capacity = vessel.pax_capacity
                    if capacity is not None:
                        actual_pax = max(0, int(capacity) + pax_delta)
                    else:
                        pax_delta_warnings.append(
                            {
                                "ship": ship,
                                "call_date": call_date,
                                "reason": "missing_vessel_pax_capacity_for_real_pax_delta",
                                "delta": pax_delta,
                            }
                        )
                        if isinstance(pax, int):
                            actual_pax = pax
                elif isinstance(pax, int):
                    actual_pax = pax
            elif isinstance(pax, int):
                planned_pax = pax

            defaults = {
                "shipping_line": line,
                "position": position,
                "eta": eta,
                "etd": etd,
                "eta_real": eta_real,
                "etd_real": etd_real,
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
                record_booking_audit(
                    existing,
                    action="operational_update",
                    summary="Reserva actualizada desde BERTHING PAPERS",
                    changes=audit_changes,
                    user=created_by,
                )
            else:
                code = resolve_unique_booking_code(
                    port,
                    line,
                    vessel,
                    datetime.strptime(call_date, "%Y-%m-%d").date(),
                    existing_codes,
                )
                existing_codes.add(code)
                booking = Booking.objects.create(
                    port=port,
                    vessel=vessel,
                    call_date=call_date,
                    booking_code=code,
                    **defaults,
                )
                created += 1
                created_booking_ids.append(booking.id)
                record_booking_audit(
                    booking,
                    action="created",
                    summary="Reserva importada desde BERTHING PAPERS",
                    changes=audit_changes,
                    user=created_by,
                )

        failures = invalid + unmatched
        _persist_batch(
            batch=batch,
            created_count=created,
            updated_count=updated,
            failures=failures,
            created_booking_ids=created_booking_ids,
        )

    if dry_run:
        would_create = 0
        would_update = 0
        for row in rows:
            call_date = row.get("call_date")
            ship = row.get("ship")
            status = row.get("status")
            if not call_date or not ship:
                invalid.append(_failure_row(row, reason="missing_call_date_or_ship"))
                continue
            if not status or status not in BookingStatus.values:
                invalid.append(
                    _failure_row(
                        row,
                        reason="unknown_status",
                        detail=str(row.get("status_raw")),
                    )
                )
                continue

            resolved, fail_reason, fail_detail = _resolve_row_catalog(row)
            if resolved is None:
                unmatched.append(
                    _failure_row(row, reason=fail_reason or "unmatched", detail=fail_detail)
                )
                continue

            port = resolved["port"]
            vessel = resolved["vessel"]
            exists = Booking.objects.filter(
                port=port,
                vessel=vessel,
                call_date=call_date,
            ).exists()
            if exists:
                would_update += 1
            else:
                would_create += 1

        failures = invalid + unmatched
        return {
            "dry_run": True,
            "parsed": len(rows),
            "would_create": would_create,
            "would_update": would_update,
            "invalid": len(invalid),
            "unmatched": len(unmatched),
            "failed": len(failures),
            "failure_rows": failures[:500],
            "would_delete": delete_data,
        }

    with transaction.atomic():
        process()

    failures = invalid + unmatched

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

    if not dry_run:
        from apps.notifications.models import Notification
        from apps.notifications.services.booking import (
            notify_bookings_bulk_created,
            notify_bookings_bulk_updated,
        )

        if created > 0:
            notify_bookings_bulk_created(
                count=created,
                port_id=None,
                batch_id=batch_id,
                artifact=Notification.Artifact.BERTHING_IMPORT,
                actor=created_by,
            )
        elif updated > 0:
            notify_bookings_bulk_updated(
                count=updated,
                port_id=None,
                artifact=Notification.Artifact.BERTHING_IMPORT,
                actor=created_by,
            )

    return {
        "batch_id": batch_id,
        "parsed": len(rows),
        "created": created,
        "updated": updated,
        "invalid": len(invalid),
        "unmatched": len(unmatched),
        "failed": len(failures),
        "failure_rows": failures[:500],
        "invalid_rows": invalid[:500],
        "unmatched_rows": unmatched[:500],
        "pax_delta_warnings": len(pax_delta_warnings),
        "pax_delta_warning_rows": pax_delta_warnings[:200],
        "deleted_before": delete_data,
        "confirmations": confirmation_report,
    }


def parse_and_write_json(xlsx_source: Path, json_path: Path) -> list[dict[str, Any]]:
    rows = parse_berthing_source(xlsx_source)
    write_parsed_json(rows, json_path)
    return rows
