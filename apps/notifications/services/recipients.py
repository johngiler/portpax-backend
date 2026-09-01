from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth import get_user_model

from apps.accounts.models import UserPortAccess, UserProfile, UserRole


def notification_recipients(
    *,
    port_id: int | None = None,
    port_ids: Iterable[int] | None = None,
    exclude_user_id: int | None = None,
):
    """Frontend users with access to the given port(s). Admins receive all."""
    User = get_user_model()
    qs = (
        User.objects.filter(is_active=True, profile__isnull=False)
        .exclude(is_superuser=True)
        .select_related("profile")
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)

    scope: set[int] | None
    if port_id is not None:
        scope = {int(port_id)}
    elif port_ids:
        scope = {int(pid) for pid in port_ids if pid}
    else:
        scope = None

    if scope is None:
        return qs

    admin_ids = set(
        qs.filter(profile__role=UserRole.ADMIN).values_list("pk", flat=True)
    )
    scoped_ids = set(
        UserPortAccess.objects.filter(port_id__in=scope).values_list(
            "user_id", flat=True
        )
    )
    return qs.filter(pk__in=admin_ids | scoped_ids)
