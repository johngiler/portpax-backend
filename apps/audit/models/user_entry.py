from django.conf import settings
from django.db import models

from apps.audit.services.deletion import ImmutableAuditModel


class UserAuditEntry(ImmutableAuditModel):
    """Audit trail for managed users (CRUD) and frontend login sessions."""

    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_as_subject",
        help_text="User the event is about (null if deleted).",
    )
    subject_username = models.CharField(max_length=150)
    subject_display = models.CharField(max_length=255, blank=True, default="")
    subject_role = models.CharField(max_length=32, blank=True, default="")
    subject_is_active = models.BooleanField(null=True, blank=True)
    action = models.CharField(max_length=64)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_as_actor",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["subject_role", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject_username} · {self.action}"
