from django.conf import settings
from django.db import models

from apps.audit.services.deletion import ImmutableAuditModel


class LtaAuditEntry(ImmutableAuditModel):
    """Audit trail for long-term agreements (CRUD + link bookings)."""

    agreement = models.ForeignKey(
        "bookings.LongTermAgreement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    agreement_code = models.CharField(max_length=64, blank=True, default="")
    agreement_name = models.CharField(max_length=255, blank=True, default="")
    port_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    port_code = models.CharField(max_length=64, blank=True, default="")
    shipping_line_code = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=64)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lta_audit_as_actor",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["agreement_code", "-created_at"]),
        ]

    def __str__(self) -> str:
        ref = self.agreement_code or self.agreement_id or "?"
        return f"{ref} · {self.action}"
