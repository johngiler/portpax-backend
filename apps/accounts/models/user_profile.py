from django.conf import settings
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    BOOKING_OPERATOR = "booking_operator", "Booking operator"
    PORT_OPERATOR = "port_operator", "Port operator"
    VIEWER = "viewer", "Viewer"


class UserProfile(models.Model):
    """MVP role for a Django auth user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=32,
        choices=UserRole.choices,
        default=UserRole.BOOKING_OPERATOR,
    )
    avatar = models.ImageField(
        upload_to="users/avatars/",
        blank=True,
        null=True,
        help_text="Profile photo thumbnail (single image).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.get_username()} ({self.role})"
