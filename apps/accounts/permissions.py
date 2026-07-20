from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import UserPortAccess, UserProfile, UserRole
from apps.accounts.services.frontend_access import (
    FRONTEND_ACCESS_DENIED,
    frontend_access_denial_message,
    user_may_use_frontend,
)


def user_role(user) -> str | None:
    """Return the user's MVP role, or None if they have no profile."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return None


def user_port_ids(user) -> set[int] | None:
    """Port IDs the user may access.

    Returns None for admin (all ports). For other roles, returns the set of
    allowed port IDs (empty set = no port access).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    if user_role(user) == UserRole.ADMIN:
        return None
    return set(
        UserPortAccess.objects.filter(user=user).values_list("port_id", flat=True)
    )


def user_can_access_port(user, port_id: int | None) -> bool:
    """True if the user may access the given port."""
    if port_id is None:
        return False
    allowed = user_port_ids(user)
    if allowed is None:
        return True
    return int(port_id) in allowed


class IsFrontendAppUser(BasePermission):
    """Allow only non-superusers with an assigned UserProfile role."""

    message = FRONTEND_ACCESS_DENIED

    def has_permission(self, request, view) -> bool:
        user = request.user
        if user_may_use_frontend(user):
            return True
        self.message = frontend_access_denial_message(user)
        return False


class IsAdminRole(BasePermission):
    """Allow only users with the admin MVP role."""

    def has_permission(self, request, view) -> bool:
        return user_role(request.user) == UserRole.ADMIN


class IsBookingOperatorOrAbove(BasePermission):
    """Allow admin, booking_operator, or port_operator (not viewer)."""

    ALLOWED = {
        UserRole.ADMIN,
        UserRole.BOOKING_OPERATOR,
        UserRole.PORT_OPERATOR,
    }

    def has_permission(self, request, view) -> bool:
        return user_role(request.user) in self.ALLOWED


class IsPortOperatorOrAdmin(BasePermission):
    """Allow port_operator or admin."""

    ALLOWED = {UserRole.ADMIN, UserRole.PORT_OPERATOR}

    def has_permission(self, request, view) -> bool:
        return user_role(request.user) in self.ALLOWED


class DenyViewerWrites(BasePermission):
    """Viewers may only use safe (read) methods."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return user_role(request.user) != UserRole.VIEWER
