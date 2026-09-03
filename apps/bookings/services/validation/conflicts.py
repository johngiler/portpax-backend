"""Persist and normalize non-blocking booking conflicts."""

from __future__ import annotations

from apps.bookings.services.validation.conflict_codes import (
    INFO_ONLY_CODES,
    severity_for_code,
)


def normalize_issue_dict(issue: dict) -> dict:
    """Ensure severity; demote former hard errors to non-blocking warnings."""
    code = str(issue.get("code") or "")
    severity = issue.get("severity") or severity_for_code(
        code, level=issue.get("level")
    )
    out = {
        "code": code,
        "message": str(issue.get("message") or ""),
        "severity": severity,
        "level": "warning" if severity != "green" else "info",
    }
    detail = issue.get("detail")
    if isinstance(detail, dict) and detail:
        out["detail"] = detail
    return out


def conflicts_from_validation(result: dict) -> list[dict]:
    """Flatten errors+warnings into normalized conflict items."""
    raw: list[dict] = []
    raw.extend(result.get("errors") or [])
    raw.extend(result.get("warnings") or [])
    seen: set[tuple] = set()
    out: list[dict] = []
    for item in raw:
        norm = normalize_issue_dict(item if isinstance(item, dict) else {})
        detail = norm.get("detail") if isinstance(norm.get("detail"), dict) else {}
        call_date = str(detail.get("call_date") or "")
        key = (norm["code"], norm["message"], call_date)
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def snapshot_sets_has_conflict(snapshot: list[dict]) -> bool:
    return any(
        item.get("severity") in ("yellow", "red")
        and item.get("code") not in INFO_ONLY_CODES
        for item in snapshot
    )


def max_snapshot_severity(snapshot: list[dict] | None) -> str | None:
    """Highest paint severity in a conflict snapshot (red > yellow > green)."""
    from apps.bookings.services.validation.conflict_codes import resolve_issue_severity

    rank = {"red": 3, "yellow": 2, "green": 1}
    best: str | None = None
    best_n = 0
    for item in snapshot or []:
        if not isinstance(item, dict):
            continue
        sev = resolve_issue_severity(item)
        n = rank.get(sev, 0)
        if n > best_n:
            best_n = n
            best = sev
    return best


def apply_nonblocking_validation(result: dict) -> dict:
    """
    Operational rules never block create/update/confirm.
    Returns conflicts with severity; valid always True.
    """
    conflicts = conflicts_from_validation(result)
    # Keep green + yellow + red visible as warnings for the UI.
    warnings = [c for c in conflicts]
    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "conflicts": [
            c for c in conflicts if c.get("code") not in INFO_ONLY_CODES or c.get("severity") == "green"
        ],
        "by_date": result.get("by_date") or {},
    }


def refresh_booking_conflicts(
    booking,
    *,
    acknowledge_combined_red: bool = False,
    user=None,
    request=None,
    notify: bool = True,
    notify_updates: bool = True,
) -> list[dict]:
    """Recompute and persist has_conflict + conflict_severity + conflict_snapshot.

    Records booking audit when conflicts are detected or cleared.
    notify: campanita on newly detected / resolved flags.
    notify_updates: campanita when an existing conflict's codes/severity change
    (skip in bulk/cron so recálculos no inundan la campanita).
    """
    from apps.audit.services.record import record_booking_audit
    from apps.bookings.services.validation import validate_booking_instance
    from apps.bookings.services.validation.conflict_codes import resolve_issue_severity

    prev_flag = bool(booking.has_conflict)
    prev_severity = getattr(booking, "conflict_severity", None) or None
    prev_snapshot = list(booking.conflict_snapshot or [])

    result = validate_booking_instance(
        booking,
        acknowledge_combined_red=acknowledge_combined_red,
        nonblocking=False,
    )
    conflicts = conflicts_from_validation(result)
    snapshot: list[dict] = []
    for item in conflicts:
        code = str(item.get("code") or "")
        if code in INFO_ONLY_CODES:
            continue
        sev = resolve_issue_severity(item)
        if sev not in ("yellow", "red"):
            continue
        normalized = dict(item)
        normalized["severity"] = sev
        snapshot.append(normalized)

    next_flag = snapshot_sets_has_conflict(snapshot)
    next_severity = max_snapshot_severity(snapshot) if next_flag else None

    booking.has_conflict = next_flag
    booking.conflict_severity = next_severity
    booking.conflict_snapshot = snapshot
    booking.save(
        update_fields=[
            "has_conflict",
            "conflict_severity",
            "conflict_snapshot",
            "updated_at",
        ]
    )

    prev_codes = {str(i.get("code") or "") for i in prev_snapshot}
    next_codes = {str(i.get("code") or "") for i in snapshot}
    snapshot_changed = (
        prev_codes != next_codes
        or prev_flag != next_flag
        or prev_severity != next_severity
    )

    if snapshot_changed:
        from apps.notifications.models import Notification
        from apps.notifications.services.booking import notify_booking_conflict

        if next_flag and not prev_flag:
            record_booking_audit(
                booking,
                action="conflict_detected",
                summary=_conflict_detected_summary(snapshot),
                changes={
                    "has_conflict": {"from": False, "to": True},
                    "conflict_severity": {"from": None, "to": next_severity},
                    "conflicts": snapshot,
                },
                user=user,
                request=request,
            )
            if notify:
                notify_booking_conflict(
                    booking,
                    event=Notification.Event.CONFLICT_DETECTED,
                    actor=user,
                )
        elif prev_flag and not next_flag:
            record_booking_audit(
                booking,
                action="conflict_resolved",
                summary="Conflictos operativos resueltos",
                changes={
                    "has_conflict": {"from": True, "to": False},
                    "conflict_severity": {"from": prev_severity, "to": None},
                    "resolved_conflicts": prev_snapshot,
                },
                user=user,
                request=request,
            )
            if notify:
                notify_booking_conflict(
                    booking,
                    event=Notification.Event.CONFLICT_RESOLVED,
                    actor=user,
                )
        elif next_flag and prev_flag and (
            prev_codes != next_codes or prev_severity != next_severity
        ):
            record_booking_audit(
                booking,
                action="conflict_updated",
                summary=_conflict_updated_summary(prev_snapshot, snapshot),
                changes={
                    "has_conflict": {"from": True, "to": True},
                    "conflict_severity": {
                        "from": prev_severity,
                        "to": next_severity,
                    },
                    "conflicts_from": prev_snapshot,
                    "conflicts_to": snapshot,
                },
                user=user,
                request=request,
            )
            if notify and notify_updates:
                notify_booking_conflict(
                    booking,
                    event=Notification.Event.CONFLICT_UPDATED,
                    actor=user,
                )

    return snapshot


def _conflict_detected_summary(snapshot: list[dict]) -> str:
    codes = [str(i.get("code") or "") for i in snapshot if i.get("code")]
    if not codes:
        return "Conflicto operativo detectado"
    if len(codes) == 1:
        return f"Conflicto detectado: {codes[0]}"
    return f"Conflictos detectados ({len(codes)}): {', '.join(codes[:4])}"


def _conflict_updated_summary(prev: list[dict], nxt: list[dict]) -> str:
    prev_codes = {str(i.get("code") or "") for i in prev}
    next_codes = {str(i.get("code") or "") for i in nxt}
    added = sorted(next_codes - prev_codes)
    removed = sorted(prev_codes - next_codes)
    parts: list[str] = []
    if added:
        parts.append(f"+{', '.join(added[:3])}")
    if removed:
        parts.append(f"−{', '.join(removed[:3])}")
    detail = " · ".join(parts) if parts else "detalle actualizado"
    return f"Conflictos actualizados ({detail})"


def refresh_booking_conflicts_for_vessel_itinerary(
    vessel_id: int,
    *,
    user=None,
    request=None,
    notify: bool = True,
    notify_updates: bool = True,
) -> int:
    """Recompute conflicts for every active booking on a vessel (geo + pier)."""
    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
    from apps.bookings.models import Booking

    qs = Booking.objects.filter(
        vessel_id=vessel_id,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    ).order_by("call_date", "id")
    count = 0
    for booking in qs.iterator(chunk_size=200):
        refresh_booking_conflicts(
            booking,
            user=user,
            request=request,
            notify=notify,
            notify_updates=notify_updates,
        )
        count += 1
    return count


def refresh_booking_conflicts_after_port_proximity_change(
    port_id: int,
    *,
    user=None,
    request=None,
) -> int:
    """
    After PortProximity rows change, refresh bookings for vessels that call
    at the affected port (multi-port geo compares the full itinerary).
    """
    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
    from apps.bookings.models import Booking

    vessel_ids = (
        Booking.objects.filter(
            port_id=port_id,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        )
        .values_list("vessel_id", flat=True)
        .distinct()
    )
    total = 0
    for vessel_id in vessel_ids:
        total += refresh_booking_conflicts_for_vessel_itinerary(
            vessel_id,
            user=user,
            request=request,
        )
    return total


def refresh_related_booking_conflicts(
    booking,
    *,
    user=None,
    request=None,
) -> None:
    """Refresh this booking and same-day pier siblings that share a recalc pair."""
    refresh_booking_conflicts(booking, user=user, request=request)
    if not booking.position_id or not booking.call_date:
        return

    from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
    from apps.bookings.models import Booking
    from apps.catalogs.models import PositionLoaRecalcRule
    from django.db.models import Q

    sibling_ids: set[int] = set()
    for rule in PositionLoaRecalcRule.objects.filter(is_active=True).filter(
        Q(position_a_id=booking.position_id) | Q(position_b_id=booking.position_id)
    ):
        sibling_ids.add(rule.position_a_id)
        sibling_ids.add(rule.position_b_id)
    sibling_ids.discard(booking.position_id)
    if not sibling_ids:
        return

    qs = Booking.objects.filter(
        call_date=booking.call_date,
        position_id__in=sibling_ids,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    ).exclude(pk=booking.pk)
    for other in qs:
        refresh_booking_conflicts(other, user=user, request=request)
