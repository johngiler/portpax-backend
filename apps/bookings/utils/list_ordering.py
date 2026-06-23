from datetime import date

from django.db.models import Case, DateField, F, Value, When
from django.utils import timezone

_FAR_FUTURE = date(9999, 12, 31)
_FAR_PAST = date(1, 1, 1)


def apply_booking_list_ordering(queryset, ordering: str | None):
    if ordering == "-call_date":
        return queryset.order_by("-call_date", "-created_at")
    if ordering == "call_date":
        return queryset.order_by("call_date", "-created_at")

    today = timezone.localdate()
    return queryset.annotate(
        _future_sort=Case(
            When(call_date__gte=today, then=F("call_date")),
            default=Value(_FAR_FUTURE),
            output_field=DateField(),
        ),
        _past_sort=Case(
            When(call_date__lt=today, then=F("call_date")),
            default=Value(_FAR_PAST),
            output_field=DateField(),
        ),
    ).order_by("_future_sort", "-_past_sort", "-created_at")
