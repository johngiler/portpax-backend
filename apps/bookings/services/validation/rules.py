from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from django.db.models import Q

from apps.bookings.constants import (
    ACTIVE_BOOKING_STATUSES,
    ETA_CLOSE_GAP_HOURS,
    MAX_OVERHANG_M,
    OCCUPATION_CONFLICT_STATUSES,
)
from apps.bookings.models import Booking, BookingStatus
from apps.catalogs.models import Port, Position, PositionNestingRule, PositionPairConstraint, Vessel

FULL_DAY_START = time(0, 0)
FULL_DAY_END = time(23, 59)


class ValidationIssue:
    def __init__(
        self,
        level: Literal["error", "warning", "info"],
        code: str,
        message: str,
        *,
        severity: str | None = None,
        detail: dict | None = None,
    ):
        self.level = level
        self.code = code
        self.message = message
        self.severity = severity
        self.detail = detail or {}

    def as_dict(self) -> dict:
        from apps.bookings.services.validation.conflict_codes import (
            severity_for_code,
        )

        severity = self.severity or severity_for_code(self.code, level=self.level)
        payload = {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "severity": severity,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload



def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def occupation_window(eta: time | None, etd: time | None) -> tuple[time, time]:
    """Missing ETA/ETD → full-day occupation (00:00–23:59)."""
    return (eta or FULL_DAY_START, etd or FULL_DAY_END)


def times_overlap(
    eta_a: time | None,
    etd_a: time | None,
    eta_b: time | None,
    etd_b: time | None,
) -> bool:
    start_a, end_a = occupation_window(eta_a, etd_a)
    start_b, end_b = occupation_window(eta_b, etd_b)
    return start_a < end_b and end_a > start_b


def window_gap(
    eta_a: time | None,
    etd_a: time | None,
    eta_b: time | None,
    etd_b: time | None,
) -> timedelta | None:
    """Gap between non-overlapping windows; None if they overlap."""
    start_a, end_a = occupation_window(eta_a, etd_a)
    start_b, end_b = occupation_window(eta_b, etd_b)
    if start_a < end_b and end_a > start_b:
        return None
    day = datetime(2000, 1, 1)
    if end_a <= start_b:
        return datetime.combine(day.date(), start_b) - datetime.combine(day.date(), end_a)
    return datetime.combine(day.date(), start_a) - datetime.combine(day.date(), end_b)


def vessel_meets_combined_min(vessel: Vessel, min_loa_m) -> bool:
    """Mega-ship when vessel LOA >= combined min_loa (e.g. 365 m)."""
    loa = _decimal(vessel.loa_m)
    min_loa = _decimal(min_loa_m)
    return loa is not None and min_loa is not None and loa >= min_loa


def mega_combined_positions(*, port_id: int, vessel: Vessel) -> list[Position]:
    """Active combined slots this vessel must use (LOA >= each slot's min_loa)."""
    from apps.catalogs.models import PositionComponent

    combined_ids = (
        PositionComponent.objects.filter(
            combined_position__port_id=port_id,
            combined_position__is_active=True,
        )
        .values_list("combined_position_id", flat=True)
        .distinct()
    )
    matches: list[Position] = []
    for slot in Position.objects.filter(id__in=combined_ids, is_active=True):
        if vessel_meets_combined_min(vessel, slot.min_loa_m):
            matches.append(slot)
    return matches


def validate_physical_fit(
    vessel: Vessel,
    position: Position | None,
    port: Port,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not position:
        return issues

    loa = _decimal(vessel.loa_m)
    from apps.catalogs.services.position_combination import position_is_combined

    # Combined catalog rows are no longer bookable (Fernanda/Herman Aug 2026).
    if position_is_combined(position):
        issues.append(
            ValidationIssue(
                "error",
                "combined_position_retired",
                f"{position.code} ya no es una posición reservable. "
                "Usa las posiciones físicas del muelle (p. ej. E1 o E2).",
            )
        )
        return issues

    from apps.bookings.services.validation.loa_recalc import pier_shared_max_loa

    slot_max = _decimal(position.max_loa_m)
    pier_max = pier_shared_max_loa(position)
    # Shared-pier rule: hard ceiling is pier max_loa; slot max is soft.
    if pier_max is not None and loa is not None:
        if loa > pier_max:
            issues.append(
                ValidationIssue(
                    "error",
                    "loa_exceeds_position",
                    f"LOA del barco ({loa} m) excede la eslora máxima del muelle "
                    f"({pier_max} m) para {position.code}.",
                )
            )
        elif slot_max is not None and loa > slot_max:
            issues.append(
                ValidationIssue(
                    "warning",
                    "loa_shared_pier",
                    f"LOA ({loa} m) supera el máximo de {position.code} ({slot_max} m); "
                    f"se recalcula la eslora restante de la posición vecina "
                    f"(máx. muelle {pier_max} m).",
                )
            )
    elif loa is not None and slot_max is not None:
        if loa > slot_max:
            over = loa - slot_max
            if over > MAX_OVERHANG_M:
                issues.append(
                    ValidationIssue(
                        "error",
                        "loa_exceeds_position",
                        f"LOA del barco ({loa} m) excede la posición {position.code} "
                        f"({slot_max} m) por más de {MAX_OVERHANG_M} m de overhang.",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "loa_overhang",
                        f"LOA ({loa} m) supera el máximo de {position.code} ({slot_max} m) "
                        f"con overhang de {over} m (límite {MAX_OVERHANG_M} m).",
                    )
                )

    beam = _decimal(vessel.beam_m)
    max_beam = _decimal(position.max_beam_m)
    if beam is not None and max_beam is not None and beam > max_beam:
        issues.append(
            ValidationIssue(
                "error",
                "beam_exceeds_position",
                f"Manga del barco ({beam} m) excede el máximo de {position.code} "
                f"({max_beam} m).",
            )
        )

    draft = _decimal(vessel.draft_m)
    # Draft is validated against the position only (not berth / port minimum).
    position_depth = _decimal(position.min_draft_m)
    if draft is not None and position_depth is not None and draft > position_depth:
        issues.append(
            ValidationIssue(
                "error",
                "draft_too_deep",
                f"Calado del barco ({draft} m) supera la profundidad disponible "
                f"({position_depth} m) en {position.code}.",
            )
        )

    return issues


def validate_multi_port_conflict(
    vessel_id: int,
    call_date,
    port_id: int,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    """Warn if the vessel has an active call at another port within ±2 days."""
    from datetime import timedelta

    window_start = call_date - timedelta(days=2)
    window_end = call_date + timedelta(days=2)
    qs = Booking.objects.filter(
        vessel_id=vessel_id,
        call_date__gte=window_start,
        call_date__lte=window_end,
        status__in=ACTIVE_BOOKING_STATUSES,
    ).exclude(port_id=port_id)
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    others = list(qs.select_related("port").order_by("call_date", "id")[:8])
    if not others:
        return []

    issues: list[ValidationIssue] = []
    for other in others:
        if other.call_date == call_date:
            message = (
                f"El mismo barco ya tiene escala en {other.port.name} "
                f"({other.booking_code}) en esta fecha."
            )
            code = "multi_port_conflict"
        else:
            message = (
                f"El mismo barco tiene escala en {other.port.name} "
                f"({other.booking_code}) el {other.call_date.isoformat()} "
                f"(±2 días). La escala actual puede no ser viable."
            )
            code = "multi_port_proximity"
        issues.append(ValidationIssue("warning", code, message))
    return issues


def related_position_ids(position_id: int) -> set[int]:
    """
    Positions that physically conflict with this slot.

    Combined E1+E2 conflicts with E1 and E2; a base pier conflicts with
    any combined slot that includes it.
    """
    from apps.catalogs.models import PositionComponent

    ids = {position_id}
    ids.update(
        PositionComponent.objects.filter(combined_position_id=position_id).values_list(
            "source_position_id",
            flat=True,
        )
    )
    ids.update(
        PositionComponent.objects.filter(source_position_id=position_id).values_list(
            "combined_position_id",
            flat=True,
        )
    )
    return ids


def find_occupying_booking(
    position_id: int,
    call_date,
    exclude_booking_id: int | None = None,
):
    """Live booking that occupies this slot or a combined/component sibling."""
    qs = Booking.objects.filter(
        position_id__in=related_position_ids(position_id),
        call_date=call_date,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    ).select_related("vessel", "shipping_line", "position", "position__port")
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    return qs.order_by("id").first()


def validate_position_availability(
    position_id: int,
    call_date,
    exclude_booking_id: int | None = None,
    *,
    eta: time | None = None,
    etd: time | None = None,
) -> list[ValidationIssue]:
    conflict_position_ids = related_position_ids(position_id)
    qs = Booking.objects.filter(
        position_id__in=conflict_position_ids,
        call_date=call_date,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    issues: list[ValidationIssue] = []
    for conflict in qs.select_related("vessel", "position"):
        if times_overlap(eta, etd, conflict.eta, conflict.etd):
            other_code = conflict.position.code if conflict.position_id else "?"
            if conflict.status == BookingStatus.CL:
                issues.append(
                    ValidationIssue(
                        "error",
                        "lta_priority_conflict",
                        f"La posición está ocupada por un call CL (LTA inamovible): "
                        f"{conflict.vessel.name} ({conflict.booking_code})"
                        + (
                            f" en {other_code}."
                            if conflict.position_id != position_id
                            else "."
                        ),
                    )
                )
            else:
                msg = (
                    f"La posición ya está asignada a {conflict.vessel.name} "
                    f"({conflict.booking_code}) en un horario solapado."
                )
                if conflict.position_id != position_id:
                    msg = (
                        f"Conflicto con {other_code}: {conflict.vessel.name} "
                        f"({conflict.booking_code}) en horario solapado "
                        f"(posición combinada / componente)."
                    )
                issues.append(
                    ValidationIssue(
                        "error",
                        "position_occupied",
                        msg,
                    )
                )
            continue

        gap = window_gap(eta, etd, conflict.eta, conflict.etd)
        if gap is not None and gap < timedelta(hours=ETA_CLOSE_GAP_HOURS):
            issues.append(
                ValidationIssue(
                    "warning",
                    "eta_close",
                    f"Menos de {ETA_CLOSE_GAP_HOURS} h entre esta escala y "
                    f"{conflict.vessel.name} ({conflict.booking_code}) en la misma posición.",
                )
            )

    return issues


def validate_min_eta(
    position: Position | None,
    eta: time | None,
) -> list[ValidationIssue]:
    if not position or not position.min_eta or eta is None:
        return []
    if eta < position.min_eta:
        return [
            ValidationIssue(
                "warning",
                "eta_before_min",
                f"ETA ({eta.strftime('%H:%M')}) es anterior al mínimo de "
                f"{position.code} ({position.min_eta.strftime('%H:%M')}).",
            )
        ]
    return []


def validate_combined_loa(
    vessel: Vessel,
    position: Position | None,
    call_date,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    if not position:
        return []

    constraints = PositionPairConstraint.objects.filter(
        port_id=position.port_id,
    ).filter(Q(position_a_id=position.id) | Q(position_b_id=position.id)).select_related(
        "position_a",
        "position_b",
    )

    issues: list[ValidationIssue] = []
    our_loa = _decimal(vessel.loa_m)
    if our_loa is None:
        return issues

    for constraint in constraints:
        other_id = (
            constraint.position_b_id
            if constraint.position_a_id == position.id
            else constraint.position_a_id
        )
        other_qs = Booking.objects.filter(
            position_id=other_id,
            call_date=call_date,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        )
        if exclude_booking_id:
            other_qs = other_qs.exclude(pk=exclude_booking_id)
        other = other_qs.select_related("vessel", "position").first()
        if not other:
            continue

        other_loa = _decimal(other.vessel.loa_m)
        if other_loa is None:
            continue

        combined = our_loa + other_loa
        max_combined = _decimal(constraint.max_loa_combined)
        hard_cap = _decimal(constraint.max_loa_hard_cap)
        if max_combined is None or hard_cap is None:
            continue

        other_code = other.position.code if other.position_id else "?"
        if combined <= max_combined:
            continue
        if combined < hard_cap:
            issues.append(
                ValidationIssue(
                    "warning",
                    "combined_loa_orange",
                    f"LOA combinada ({combined} m) con {other_code} supera "
                    f"{max_combined} m pero está bajo el tope duro ({hard_cap} m).",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    "error",
                    "combined_loa_red",
                    f"LOA combinada ({combined} m) con {other_code} alcanza o supera "
                    f"el tope duro ({hard_cap} m). Requiere autorización de port-operator.",
                )
            )

    return issues


def validate_filo_nesting(
    position: Position | None,
    call_date,
    *,
    eta: time | None = None,
    etd: time | None = None,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    """
    First-in / last-out when both nested positions are occupied the same day.

    outer (entrance) must arrive first; inner (fondo) must not arrive earlier.
    Optionally inner must depart before or with outer (last-out).
    """
    if not position:
        return []

    rules = (
        PositionNestingRule.objects.filter(port_id=position.port_id, is_active=True)
        .filter(Q(outer_position_id=position.id) | Q(inner_position_id=position.id))
        .select_related("outer_position", "inner_position")
    )
    if not rules:
        return []

    issues: list[ValidationIssue] = []
    for rule in rules:
        sibling_id = (
            rule.inner_position_id
            if position.id == rule.outer_position_id
            else rule.outer_position_id
        )
        sibling = Booking.objects.filter(
            position_id=sibling_id,
            call_date=call_date,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        ).select_related("vessel", "position")
        if exclude_booking_id:
            sibling = sibling.exclude(pk=exclude_booking_id)
        other = sibling.first()
        if not other:
            continue

        if position.id == rule.outer_position_id:
            outer_eta, outer_etd = eta, etd
            inner_eta, inner_etd = other.eta, other.etd
            outer_label = position.code
            inner_label = other.position.code if other.position_id else rule.inner_position.code
        else:
            outer_eta, outer_etd = other.eta, other.etd
            inner_eta, inner_etd = eta, etd
            outer_label = other.position.code if other.position_id else rule.outer_position.code
            inner_label = position.code

        if rule.enforce_eta and outer_eta is not None and inner_eta is not None:
            if inner_eta < outer_eta:
                issues.append(
                    ValidationIssue(
                        "error",
                        "filo_eta_violation",
                        f"First-in / last-out: {inner_label} no puede arribar "
                        f"({inner_eta.strftime('%H:%M')}) antes que {outer_label} "
                        f"({outer_eta.strftime('%H:%M')}).",
                    )
                )

        if rule.enforce_etd and outer_etd is not None and inner_etd is not None:
            if inner_etd > outer_etd:
                issues.append(
                    ValidationIssue(
                        "error",
                        "filo_etd_violation",
                        f"First-in / last-out: {inner_label} no puede zarpar "
                        f"({inner_etd.strftime('%H:%M')}) después que {outer_label} "
                        f"({outer_etd.strftime('%H:%M')}).",
                    )
                )

    return issues


def validate_lta(
    port: Port,
    vessel: Vessel,
    call_date,
    position: Position | None = None,
) -> list[ValidationIssue]:
    """
    LTA seasonal windows + strategic slot ownership.

    Only applies when the port has at least one active LTA agreement.
    Ports without LTAs are open booking for all dates (no LTA horizon/slot rules).

    Windows (Especificaciones LTA — Winter/Summer), when LTAs exist for the port:
    - Current + general: open market (any carrier).
    - LTA covered: only matching LTA holders; foreign weekday+position is reserved.
    - Beyond LTA covered: blocked.

    Cadence (interval_days) is enforced via agreement matching.
    """
    from datetime import date as date_cls

    from apps.bookings.services.lta.matching import (
        find_best_matching_agreement,
        find_foreign_slot_agreements,
        port_has_active_agreements,
    )
    from apps.bookings.services.lta.windows import (
        BookingWindowZone,
        compute_seasonal_windows,
        lta_holder_allows,
        open_market_allows,
    )

    if not port_has_active_agreements(port.id):
        return []

    issues: list[ValidationIssue] = []
    today = date_cls.today()
    shipping_line_id = vessel.shipping_line_id
    windows = compute_seasonal_windows(today)
    zone = windows.zone_for(call_date)

    # Strategic LTA slots apply only in the LTA covered window — not in
    # current/general open booking (anyone may take the weekday+position there).
    if zone == BookingWindowZone.LTA_COVERED:
        foreign = find_foreign_slot_agreements(
            port_id=port.id,
            shipping_line_id=shipping_line_id,
            call_date=call_date,
            position=position,
        )
        if foreign:
            other = foreign[0]
            issues.append(
                ValidationIssue(
                    "error",
                    "lta_slot_reserved",
                    f"La posición está reservada por el LTA {other.code} "
                    f"({other.shipping_line.code}) en este día de la semana.",
                )
            )

    own = find_best_matching_agreement(
        port_id=port.id,
        shipping_line_id=shipping_line_id,
        vessel=vessel,
        call_date=call_date,
        position=position,
    )

    if own:
        if not lta_holder_allows(call_date, today):
            issues.append(
                ValidationIssue(
                    "error",
                    "lta_beyond_horizon",
                    f"La fecha supera la ventana LTA cubierta "
                    f"({windows.lta_to.isoformat()}) para el acuerdo {own.code}.",
                )
            )
        return issues

    # No matching LTA: open market only (current + general).
    if zone == BookingWindowZone.BEYOND:
        issues.append(
            ValidationIssue(
                "error",
                "lta_beyond_horizon",
                f"No se puede reservar después de {windows.lta_to.isoformat()} "
                "sin un acuerdo LTA vigente.",
            )
        )
    elif zone == BookingWindowZone.LTA_COVERED or not open_market_allows(
        call_date, today
    ):
        issues.append(
            ValidationIssue(
                "error",
                "lta_horizon_denied",
                f"Entre {windows.lta_from.isoformat()} y {windows.lta_to.isoformat()} "
                "solo navieras con LTA vigente pueden reservar esta escala.",
            )
        )

    return issues


def validate_booking(
    *,
    port: Port,
    vessel: Vessel,
    call_date,
    position: Position | None = None,
    eta: time | None = None,
    etd: time | None = None,
    exclude_booking_id: int | None = None,
    acknowledge_combined_red: bool = False,
) -> dict:
    issues: list[ValidationIssue] = []
    issues.extend(validate_multi_port_conflict(vessel.id, call_date, port.id, exclude_booking_id))
    issues.extend(validate_lta(port, vessel, call_date, position))
    if position:
        issues.extend(
            validate_position_availability(
                position.id,
                call_date,
                exclude_booking_id,
                eta=eta,
                etd=etd,
            )
        )
        issues.extend(validate_physical_fit(vessel, position, port))
        issues.extend(validate_min_eta(position, eta))
        issues.extend(validate_combined_loa(vessel, position, call_date, exclude_booking_id))
        issues.extend(
            validate_filo_nesting(
                position,
                call_date,
                eta=eta,
                etd=etd,
                exclude_booking_id=exclude_booking_id,
            )
        )
        from apps.bookings.services.validation.loa_recalc import validate_loa_recalc

        issues.extend(
            validate_loa_recalc(
                vessel,
                position,
                call_date,
                eta=eta,
                etd=etd,
                exclude_booking_id=exclude_booking_id,
            )
        )

    if acknowledge_combined_red:
        for issue in issues:
            if issue.code == "combined_loa_red" and issue.level == "error":
                issue.level = "warning"
                issue.severity = "red"

    raw_errors = [i.as_dict() for i in issues if i.level == "error"]
    raw_warnings = [i.as_dict() for i in issues if i.level in ("warning", "info")]
    from apps.bookings.services.validation.conflicts import apply_nonblocking_validation

    return apply_nonblocking_validation(
        {
            "errors": raw_errors,
            "warnings": raw_warnings,
            "valid": len(raw_errors) == 0,
        }
    )
