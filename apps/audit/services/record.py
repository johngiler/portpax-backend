from apps.audit.models import (
    BookingAuditEntry,
    LtaAuditEntry,
    PortAuditEntry,
    ShippingLineAuditEntry,
    UserAuditEntry,
)
from apps.audit.services.context import with_audit_context


def _booking_entity_snapshot(booking) -> dict:
    entity = {
        "booking_code": getattr(booking, "booking_code", "") or "",
        "port_id": getattr(booking, "port_id", None),
        "call_date": str(booking.call_date) if getattr(booking, "call_date", None) else None,
        "status": getattr(booking, "status", None),
    }
    port = getattr(booking, "port", None)
    if port is not None:
        entity["port_code"] = getattr(port, "code", "") or ""
        entity["port_name"] = getattr(port, "name", "") or ""
    vessel = getattr(booking, "vessel", None)
    if vessel is not None:
        entity["vessel_name"] = getattr(vessel, "name", "") or ""
    position = getattr(booking, "position", None)
    if position is not None:
        entity["position_code"] = getattr(position, "code", "") or ""
    return entity


def record_booking_audit(
    booking,
    action: str,
    summary: str,
    changes: dict | None = None,
    user=None,
    request=None,
) -> BookingAuditEntry:
    booking_code = getattr(booking, "booking_code", "") or ""
    port_id = getattr(booking, "port_id", None)
    return BookingAuditEntry.objects.create(
        booking=booking,
        booking_code=booking_code,
        port_id=port_id,
        action=action,
        summary=summary,
        changes=with_audit_context(
            changes,
            request,
            entity=_booking_entity_snapshot(booking),
        ),
        user=user,
    )


def record_user_audit(
    *,
    action: str,
    summary: str,
    subject=None,
    subject_username: str = "",
    subject_display: str = "",
    subject_role: str = "",
    subject_is_active: bool | None = None,
    changes: dict | None = None,
    actor=None,
    request=None,
) -> UserAuditEntry:
    username = subject_username or (
        subject.get_username() if subject is not None else ""
    )
    entity = {
        "username": username,
        "display": subject_display or username,
        "role": subject_role or "",
        "is_active": subject_is_active,
    }
    return UserAuditEntry.objects.create(
        subject=subject,
        subject_username=username,
        subject_display=subject_display,
        subject_role=subject_role or "",
        subject_is_active=subject_is_active,
        action=action,
        summary=summary,
        changes=with_audit_context(changes, request, entity=entity),
        actor=actor,
    )


def record_lta_audit(
    *,
    action: str,
    summary: str,
    agreement=None,
    agreement_code: str = "",
    agreement_name: str = "",
    port_id: int | None = None,
    port_code: str = "",
    shipping_line_code: str = "",
    changes: dict | None = None,
    actor=None,
    request=None,
    entity: dict | None = None,
) -> LtaAuditEntry:
    code = agreement_code or (
        getattr(agreement, "code", "") if agreement is not None else ""
    )
    name = agreement_name or (
        getattr(agreement, "name", "") if agreement is not None else ""
    )
    if agreement is not None:
        if port_id is None:
            port_id = getattr(agreement, "port_id", None)
        if not port_code:
            port = getattr(agreement, "port", None)
            port_code = getattr(port, "code", "") or ""
        if not shipping_line_code:
            line = getattr(agreement, "shipping_line", None)
            shipping_line_code = getattr(line, "code", "") or ""
    entity_payload = entity or {
        "code": code,
        "name": name,
        "port_code": port_code,
        "shipping_line_code": shipping_line_code,
    }
    return LtaAuditEntry.objects.create(
        agreement=agreement,
        agreement_code=code,
        agreement_name=name,
        port_id=port_id,
        port_code=port_code or "",
        shipping_line_code=shipping_line_code or "",
        action=action,
        summary=summary,
        changes=with_audit_context(changes, request, entity=entity_payload),
        actor=actor,
    )


def record_port_audit(
    *,
    action: str,
    summary: str,
    port=None,
    port_code: str = "",
    port_name: str = "",
    subject_port_id: int | None = None,
    changes: dict | None = None,
    actor=None,
    request=None,
    entity: dict | None = None,
) -> PortAuditEntry:
    code = port_code or (getattr(port, "code", "") if port is not None else "")
    name = port_name or (getattr(port, "name", "") if port is not None else "")
    if subject_port_id is None and port is not None:
        subject_port_id = port.pk
    entity_payload = entity or {"code": code, "name": name}
    return PortAuditEntry.objects.create(
        port=port,
        subject_port_id=subject_port_id,
        port_code=code or "",
        port_name=name or "",
        action=action,
        summary=summary,
        changes=with_audit_context(changes, request, entity=entity_payload),
        actor=actor,
    )


def record_shipping_line_audit(
    *,
    action: str,
    summary: str,
    shipping_line=None,
    shipping_line_code: str = "",
    shipping_line_name: str = "",
    group_name: str = "",
    changes: dict | None = None,
    actor=None,
    request=None,
    entity: dict | None = None,
) -> ShippingLineAuditEntry:
    code = shipping_line_code or (
        getattr(shipping_line, "code", "") if shipping_line is not None else ""
    )
    name = shipping_line_name or (
        getattr(shipping_line, "name", "") if shipping_line is not None else ""
    )
    if not group_name and shipping_line is not None:
        group = getattr(shipping_line, "group", None)
        group_name = getattr(group, "name", "") or ""
    entity_payload = entity or {
        "code": code,
        "name": name,
        "group_name": group_name,
    }
    return ShippingLineAuditEntry.objects.create(
        shipping_line=shipping_line,
        shipping_line_code=code or "",
        shipping_line_name=name or "",
        group_name=group_name or "",
        action=action,
        summary=summary,
        changes=with_audit_context(changes, request, entity=entity_payload),
        actor=actor,
    )
