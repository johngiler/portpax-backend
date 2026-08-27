"""Celery task discovery entry for apps.bookings."""

from apps.bookings.tasks_lta import (  # noqa: F401
    lta_destroy_agreement,
    lta_link_matching,
    lta_resync_agreement,
)
