"""Rules for who may use the PortPax frontend API (JWT)."""

from apps.accounts.models import UserProfile

# Generic on purpose: do not reveal superuser vs missing role vs bad password.
FRONTEND_ACCESS_DENIED = "No active account found with the given credentials"


def user_may_use_frontend(user) -> bool:
    """True if the user may authenticate against the frontend API."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    return UserProfile.objects.filter(user_id=user.pk).exists()


def frontend_access_denial_message(_user=None) -> str:
    """Public denial text — never discloses why access was refused."""
    return FRONTEND_ACCESS_DENIED
