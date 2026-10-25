from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth import get_user_model

from apps.accounts.models import UserRole

# Campanita: admin-only until per-role leveling is defined.
IN_APP_NOTIFICATION_ROLES: frozenset[str] = frozenset({UserRole.ADMIN})


def notification_recipients(
    *,
    port_id: int | None = None,
    port_ids: Iterable[int] | None = None,
    exclude_user_id: int | None = None,
):
    """Frontend users who should get campanita rows.

    Currently admin-only. ``port_id`` / ``port_ids`` stay in the signature for
    the later per-role leveling (operators scoped to their ports).
    """
    del port_id, port_ids
    User = get_user_model()
    qs = (
        User.objects.filter(
            is_active=True,
            profile__isnull=False,
            profile__role__in=IN_APP_NOTIFICATION_ROLES,
        )
        .exclude(is_superuser=True)
        .select_related("profile")
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    return qs
