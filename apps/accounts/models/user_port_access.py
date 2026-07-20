from django.conf import settings
from django.db import models


class UserPortAccess(models.Model):
    """Explicit port access for non-admin users.

    Admin always sees all ports (no rows required).
    Other roles with zero rows have no port access.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="port_access",
    )
    port = models.ForeignKey(
        "catalogs.Port",
        on_delete=models.CASCADE,
        related_name="user_access",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username", "port__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "port"],
                name="accounts_unique_user_port_access",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.get_username()} → {self.port}"
