def apply_booking_list_ordering(queryset, ordering: str | None):
    if ordering == "-call_date":
        return queryset.order_by("-call_date", "-created_at")
    # Default and "call_date" / "call_date_proximity": chronological ascending.
    # Nearest upcoming in calendar order — never interleave by |days from today|.
    return queryset.order_by("call_date", "id")
