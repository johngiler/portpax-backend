"""Booking list / global search including historical booking codes."""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q, QuerySet
from rest_framework import filters

from apps.audit.models import BookingAuditEntry


def booking_matches_search_term(term: str) -> Q:
    """
    Match current nomenclature fields OR any past booking_code in audit.

    Historical codes live on BookingAuditEntry.booking_code (snapshot at
    write time) and on changes.booking_code.from when the code was renamed.
    """
    term = (term or "").strip()
    if not term:
        return Q()

    history = BookingAuditEntry.objects.filter(booking_id=OuterRef("pk")).filter(
        Q(booking_code__icontains=term)
        | Q(changes__booking_code__from__icontains=term)
    )
    return (
        Q(booking_code__icontains=term)
        | Q(port__name__icontains=term)
        | Q(port__code__icontains=term)
        | Q(shipping_line__name__icontains=term)
        | Q(vessel__name__icontains=term)
        | Exists(history)
    )


def apply_booking_text_search(qs: QuerySet, raw: str) -> QuerySet:
    """AND space-separated terms (same shape as DRF SearchFilter)."""
    terms = [t for t in (raw or "").split() if t]
    if not terms:
        return qs
    combined = booking_matches_search_term(terms[0])
    for term in terms[1:]:
        combined &= booking_matches_search_term(term)
    return qs.filter(combined).distinct()


class BookingSearchFilter(filters.SearchFilter):
    """SearchFilter that also hits previous booking codes from audit history."""

    def filter_queryset(self, request, queryset, view):
        search_terms = self.get_search_terms(request)
        if not search_terms:
            return queryset
        combined = booking_matches_search_term(search_terms[0])
        for term in search_terms[1:]:
            combined &= booking_matches_search_term(term)
        return queryset.filter(combined).distinct()
