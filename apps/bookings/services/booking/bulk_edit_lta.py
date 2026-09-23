"""Claim reserved LTA slots during mass edit (same product rule as mass create)."""

from __future__ import annotations

from datetime import date

from apps.bookings.constants import LTA_SOFT_FAIL_CODES
from apps.bookings.models import Booking, BookingStatus, CancellationReason
from apps.bookings.services.booking.status import update_booking_status
from apps.bookings.services.import_mass.position_lta import (
    resolve_position_and_lta,
    serialize_lta_space_candidate,
)

CLAIM_SKIP_CODES = frozenset(
    {"position_occupied", "lta_slot_reserved", *LTA_SOFT_FAIL_CODES}
)


def _claim_lta_space_flag(payload: dict | None) -> bool:
    if not payload:
        return False
    return bool(payload.get("claim_lta_space") or payload.get("replace_lta"))


def attach_bulk_edit_lta_claim(
    *,
    port_id: int,
    vessel_id: int,
    shipping_line_id: int,
    call_date: date,
    preferred_position_id: int | None,
    claim_lta_space: bool,
    exclude_booking_id: int,
    blocking: list[dict],
    warnings: list[dict],
    status_value: str,
) -> tuple[str, dict]:
    """
    Detect claimable LTA for this group/port/date and, if not marked, block
    with the same copy as mass create. When claiming, drop occupancy / LTA
    slot errors against that placeholder.
    """
    pos = resolve_position_and_lta(
        port_id=port_id,
        vessel_id=vessel_id,
        shipping_line_id=shipping_line_id,
        call_date=call_date,
        preferred_position_id=preferred_position_id,
        claim_lta_space=claim_lta_space,
        exclude_booking_id=exclude_booking_id,
    )
    candidate = pos.get("lta_space_candidate")
    claiming = bool(claim_lta_space and candidate)

    existing = (
        Booking.objects.filter(
            port_id=port_id,
            vessel_id=vessel_id,
            call_date=call_date,
        )
        .exclude(pk=exclude_booking_id)
        .exclude(status=BookingStatus.C)
        .select_related("vessel", "position", "port", "shipping_line")
        .first()
    )
    if existing is not None and existing.status == BookingStatus.LTA:
        if not candidate:
            candidate = serialize_lta_space_candidate(existing)
            pos["lta_space_candidate"] = candidate
        if not claiming:
            pos_label = ""
            if candidate and candidate.get("position_code"):
                pos_label = f" en {candidate['position_code']}"
            blocking.append(
                {
                    "code": "lta_slot_reserved",
                    "message": (
                        f"Hay un espacio LTA de esta naviera ({existing.booking_code}"
                        f"{pos_label}). Marca «Reclamar espacio LTA» para actualizarlo "
                        "a Confirmada LTA."
                    ),
                    "severity": "yellow",
                    "level": "error",
                }
            )
    elif candidate and not claiming:
        line_name = candidate.get("shipping_line_name") or "esta naviera"
        pos_label = candidate.get("position_code") or "posición"
        blocking.append(
            {
                "code": "lta_slot_reserved",
                "message": (
                    f"Hay un espacio LTA de {line_name} esperándote en {pos_label} "
                    f"({candidate.get('booking_code')}). "
                    "Marca «Reclamar espacio LTA» para actualizarlo a Confirmada LTA."
                ),
                "severity": "yellow",
                "level": "error",
            }
        )

    lta_count = int(pos.get("lta_space_count") or 0)
    if claiming and lta_count > 1:
        cand_pos = (candidate or {}).get("position_code") if candidate else None
        cand_pos_id = (candidate or {}).get("position_id") if candidate else None
        if (
            preferred_position_id is not None
            and cand_pos_id is not None
            and int(cand_pos_id) == preferred_position_id
            and cand_pos
        ):
            warn = (
                f"Hay {lta_count} reservas LTA de este grupo en esta fecha; "
                f"se reclamará la de {cand_pos} (posición elegida)."
            )
        else:
            warn = (
                f"Hay {lta_count} reservas LTA de este grupo en esta fecha; "
                "se reclamará la más antigua."
            )
        if not any(w.get("message") == warn for w in warnings if isinstance(w, dict)):
            warnings.append(
                {
                    "code": "lta_multiple_slots",
                    "message": warn,
                    "severity": "yellow",
                    "level": "warning",
                }
            )

    if claiming:
        status_value = BookingStatus.CL
        skip = CLAIM_SKIP_CODES
        kept: list[dict] = []
        for item in blocking:
            if isinstance(item, dict) and (item.get("code") or "") in skip:
                continue
            if isinstance(item, dict) and is_lta_claim_prompt(item.get("message") or ""):
                continue
            kept.append(item)
        blocking[:] = kept

    pos["claim_lta_space"] = claiming
    return status_value, pos


def is_lta_claim_prompt(message: str) -> bool:
    return "Reclamar espacio LTA" in message or "Hay un espacio LTA" in message


def consume_claimed_lta_placeholder(
    candidate_id: int,
    *,
    claimed_by: Booking,
    user=None,
    request=None,
    audit_extra: dict | None = None,
) -> int | None:
    """
    Free the LTA ghost so the edited booking can move onto that slot.
    Returns the agreement id to keep on the moving booking, if any.
    """
    if not candidate_id or candidate_id == claimed_by.pk:
        return None
    placeholder = (
        Booking.objects.select_related("long_term_agreement")
        .filter(pk=candidate_id, status=BookingStatus.LTA)
        .first()
    )
    if placeholder is None:
        return None
    agreement_id = placeholder.long_term_agreement_id
    extra = dict(audit_extra or {})
    extra["claimed_lta_space"] = True
    extra["claimed_by_booking_id"] = claimed_by.id
    extra["claimed_by"] = claimed_by.booking_code
    update_booking_status(
        placeholder,
        BookingStatus.C,
        user=user,
        request=request,
        cancellation_reason=CancellationReason.LTA_CLAIMED,
        require_lta_agreement=False,
        audit_source="bulk_edit",
        audit_extra=extra,
    )
    return agreement_id


def claim_candidate_id(payload: dict | None) -> int | None:
    if not payload or not _claim_lta_space_flag(payload):
        return None
    candidate = payload.get("lta_space_candidate") or payload.get(
        "lta_replace_candidate"
    )
    if isinstance(candidate, dict) and candidate.get("id") is not None:
        try:
            return int(candidate["id"])
        except (TypeError, ValueError):
            return None
    return None
