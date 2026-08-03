from django.conf import settings
from django.db import models

from apps.audit.services.deletion import ImmutableAuditModel


class PortAuditEntry(ImmutableAuditModel):
    """Audit trail for port catalog CRUD."""

    port = models.ForeignKey(
        "catalogs.Port",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    # Survives port deletion for ACL filters (FK port_id is nulled).
    subject_port_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    port_code = models.CharField(max_length=64, blank=True, default="")
    port_name = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=64)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="port_audit_as_actor",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["port_code", "-created_at"]),
        ]

    def __str__(self) -> str:
        ref = self.port_code or self.subject_port_id or self.port_id or "?"
        return f"{ref} · {self.action}"
