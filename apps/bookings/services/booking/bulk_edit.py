"""Bulk edit existing bookings (list selection → mass modify)."""

from __future__ import annotations

from datetime import date, time

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.identity import (
    GROUP_MISMATCH_MESSAGE,
    update_booking_identity,
)
from apps.bookings.services.booking.status import (
    BookingStatusError,
    BookingValidationError,
    update_booking_operational,
    update_booking_status,
)
from apps.bookings.services.validation import validate_booking_params
from apps.catalogs.models import Port, Position, ShippingLine, Vessel


EDITABLE_STATUSES = frozenset(
    {
        BookingStatus.NR,
        BookingStatus.H,
        BookingStatus.CO,
        BookingStatus.CL,
        BookingStatus.LTA,
        BookingStatus.LTD,
    }
)


def _parse_time(value) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _identity_blocking_issues(
    booking: Booking,
    *,
    port_id: int,
    shipping_line_id: int,
    vessel_id: int,
    call_date: date,
) -> list[dict]:
    issues: list[dict] = []
    if booking.status == BookingStatus.C:
        issues.append(
            {
                "code": "booking_cancelled",
                "message": "No se puede editar una reserva cancelada.",
                "severity": "red",
                "level": "error",
            }
        )
        return issues

    try:
        new_line = ShippingLine.objects.get(pk=shipping_line_id)
    except ShippingLine.DoesNotExist:
        issues.append(
            {
                "code": "not_found",
                "message": "Naviera no encontrada.",
                "severity": "red",
                "level": "error",
            }
        )
        return issues

    if new_line.group_id != booking.shipping_line.group_id:
        issues.append(
            {
                "code": "shipping_line_group_mismatch",
                "message": GROUP_MISMATCH_MESSAGE,
                "severity": "red",
                "level": "error",
            }
        )

    try:
        vessel = Vessel.objects.get(pk=vessel_id)
    except Vessel.DoesNotExist:
        issues.append(
            {
                "code": "not_found",
                "message": "Barco no encontrado.",
                "severity": "red",
                "level": "error",
            }
        )
        return issues

    if vessel.shipping_line_id != shipping_line_id:
        issues.append(
            {
                "code": "vessel_line_mismatch",
                "message": "El barco debe pertenecer a la naviera seleccionada.",
                "severity": "red",
                "level": "error",
            }
        )

    clash = (
        Booking.objects.filter(
            port_id=port_id,
            vessel_id=vessel_id,
            call_date=call_date,
        )
        .exclude(pk=booking.pk)
        .first()
    )
    if clash is not None:
        issues.append(
            {
                "code": "duplicate_port_vessel_date",
                "message": (
                    f"Ya existe una reserva para ese puerto, barco y fecha "
                    f"({clash.booking_code})."
                ),
                "severity": "red",
                "level": "error",
            }
        )

    return issues


def revalidate_bulk_edit_row(payload: dict) -> dict:
    """Validate one edited booking row; return structured issues (non-blocking ops)."""
    booking_id = int(payload["booking_id"])
    booking = Booking.objects.select_related(
        "port",
        "shipping_line",
        "shipping_line__group",
        "vessel",
        "position",
    ).get(pk=booking_id)

    port_id = int(payload.get("port_id") or booking.port_id)
    shipping_line_id = int(payload.get("shipping_line_id") or booking.shipping_line_id)
    vessel_id = int(payload.get("vessel_id") or booking.vessel_id)
    call_date = _parse_date(payload.get("call_date")) or booking.call_date
    eta = _parse_time(payload.get("eta")) if "eta" in payload else booking.eta
    etd = _parse_time(payload.get("etd")) if "etd" in payload else booking.etd
    position_raw = payload.get("position_id", booking.position_id)
    position_id = int(position_raw) if position_raw not in (None, "", 0) else None
    status_value = payload.get("status") or booking.status
    notes = payload.get("notes") if "notes" in payload else booking.notes

    blocking = _identity_blocking_issues(
        booking,
        port_id=port_id,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        call_date=call_date,
    )

    warnings: list[dict] = []
    if not blocking:
        result = validate_booking_params(
            port_id=port_id,
            vessel_id=vessel_id,
            call_dates=[call_date],
            position_id=position_id,
            eta=eta,
            etd=etd,
            exclude_booking_id=booking.id,
        )
        warnings = list(result.get("warnings") or result.get("conflicts") or [])

    selectable = len(blocking) == 0 and booking.status != BookingStatus.C
    port = Port.objects.filter(pk=port_id).first()
    shipping_line = ShippingLine.objects.filter(pk=shipping_line_id).first()
    vessel = Vessel.objects.filter(pk=vessel_id).first()
    position = (
        Position.objects.filter(pk=position_id).first() if position_id else None
    )
    return {
        "booking_id": booking.id,
        "booking_code": booking.booking_code,
        "port_id": port_id,
        "port_name": port.name if port else None,
        "port_code": port.code if port else None,
        "shipping_line_id": shipping_line_id,
        "shipping_line_name": shipping_line.name if shipping_line else None,
        "shipping_line_group": (
            shipping_line.group_id if shipping_line else None
        ),
        "vessel_id": vessel_id,
        "vessel_name": vessel.name if vessel else None,
        "call_date": call_date.isoformat(),
        "eta": eta.strftime("%H:%M") if eta else None,
        "etd": etd.strftime("%H:%M") if etd else None,
        "position_id": position_id,
        "position_code": position.code if position else None,
        "status": status_value,
        "notes": notes or "",
        "blocking_issues": blocking,
        "warnings": warnings,
        "selectable": selectable,
    }


def apply_bulk_edit_rows(
    rows: list[dict],
    *,
    user=None,
    request=None,
) -> dict:
    updated: list[dict] = []
    failed: list[dict] = []

    for payload in rows:
        booking_id = payload.get("booking_id")
        try:
            booking_id = int(booking_id)
            booking = Booking.objects.select_related(
                "port",
                "shipping_line",
                "shipping_line__group",
                "vessel",
                "position",
            ).get(pk=booking_id)
        except (TypeError, ValueError, Booking.DoesNotExist):
            failed.append(
                {
                    "booking_id": booking_id,
                    "detail": "Reserva no encontrada.",
                }
            )
            continue

        try:
            port_id = int(payload.get("port_id") or booking.port_id)
            shipping_line_id = int(
                payload.get("shipping_line_id") or booking.shipping_line_id
            )
            vessel_id = int(payload.get("vessel_id") or booking.vessel_id)
            call_date = _parse_date(payload.get("call_date")) or booking.call_date
            notes = payload["notes"] if "notes" in payload else None
            eta = (
                _parse_time(payload.get("eta"))
                if "eta" in payload
                else booking.eta
            )
            etd = (
                _parse_time(payload.get("etd"))
                if "etd" in payload
                else booking.etd
            )
            if "position_id" in payload:
                pos_raw = payload.get("position_id")
                position_id = (
                    int(pos_raw) if pos_raw not in (None, "", 0) else None
                )
            else:
                position_id = booking.position_id
            new_status = payload.get("status")

            booking = update_booking_identity(
                booking,
                user=user,
                request=request,
                port_id=port_id,
                shipping_line_id=shipping_line_id,
                vessel_id=vessel_id,
                call_date=call_date,
                notes=notes,
            )
            booking = update_booking_operational(
                booking,
                user=user,
                request=request,
                position_id=position_id,
                eta=eta,
                etd=etd,
            )
            if (
                new_status
                and new_status != booking.status
                and new_status in EDITABLE_STATUSES
            ):
                booking = update_booking_status(
                    booking,
                    new_status,
                    user=user,
                    request=request,
                    require_lta_agreement=False,
                )
            updated.append(
                {
                    "booking_id": booking.id,
                    "booking_code": booking.booking_code,
                }
            )
        except BookingValidationError as exc:
            msg = str(exc)
            if exc.errors:
                first = exc.errors[0]
                if isinstance(first, dict) and first.get("message"):
                    msg = str(first["message"])
            failed.append({"booking_id": booking_id, "detail": msg, "errors": exc.errors})
        except BookingStatusError as exc:
            failed.append({"booking_id": booking_id, "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 — per-row isolation
            failed.append({"booking_id": booking_id, "detail": str(exc)})

    return {
        "updated_count": len(updated),
        "failed_count": len(failed),
        "updated": updated,
        "failed": failed,
    }


def bookings_to_edit_rows(bookings: list[Booking]) -> list[dict]:
    """Initial payload for the mass-edit modal grid."""
    rows = []
    for booking in bookings:
        if booking.status == BookingStatus.C:
            continue
        revalidated = revalidate_bulk_edit_row(
            {
                "booking_id": booking.id,
                "port_id": booking.port_id,
                "shipping_line_id": booking.shipping_line_id,
                "vessel_id": booking.vessel_id,
                "call_date": booking.call_date.isoformat(),
                "eta": booking.eta.strftime("%H:%M") if booking.eta else None,
                "etd": booking.etd.strftime("%H:%M") if booking.etd else None,
                "position_id": booking.position_id,
                "status": booking.status,
                "notes": booking.notes or "",
            }
        )
        rows.append(revalidated)
    return rows
