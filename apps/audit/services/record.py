from apps.audit.models import BookingAuditEntry


def record_booking_audit(
    booking,
    action: str,
    summary: str,
    changes: dict | None = None,
    user=None,
) -> BookingAuditEntry:
    return BookingAuditEntry.objects.create(
        booking=booking,
        action=action,
        summary=summary,
        changes=changes or {},
        user=user,
    )
