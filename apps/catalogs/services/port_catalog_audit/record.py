from apps.audit.services.record import record_port_audit


def record_port_child_audit(
    *,
    action: str,
    summary: str,
    port,
    changes: dict | None = None,
    entity: dict | None = None,
    actor=None,
    request=None,
):
    return record_port_audit(
        action=action,
        summary=summary,
        port=port,
        subject_port_id=port.pk,
        port_code=port.code or "",
        port_name=port.name or "",
        changes=changes,
        entity=entity,
        actor=actor,
        request=request,
    )
