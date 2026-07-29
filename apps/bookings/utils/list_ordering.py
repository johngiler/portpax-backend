from django.db import connection
from django.db.models.expressions import RawSQL
from django.utils import timezone


def apply_booking_list_ordering(queryset, ordering: str | None):
    if ordering == "-call_date":
        return queryset.order_by("-call_date", "-created_at")
    if ordering == "call_date":
        return queryset.order_by("call_date", "created_at")

    # Default: nearest to today first (past or future), then chronological.
    today = timezone.localdate().isoformat()
    if connection.vendor == "sqlite":
        proximity = RawSQL(
            "ABS(julianday(call_date) - julianday(%s))",
            (today,),
        )
    else:
        # PostgreSQL / MySQL: date subtraction yields days.
        proximity = RawSQL("ABS(call_date - %s)", (today,))

    return queryset.annotate(_proximity=proximity).order_by(
        "_proximity",
        "call_date",
        "id",
    )
