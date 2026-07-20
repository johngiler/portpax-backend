"""Sidebar navigation entity counts."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsFrontendAppUser, user_port_ids, user_role
from apps.bookings.models import Booking
from apps.catalogs.models import Port, ShippingLine

User = get_user_model()

# Kept for API consumers / docs; badge uses YTD bookings instead.
REPORT_MODULE_COUNT = 3


class NavCountsView(APIView):
    """Lightweight counts for sidebar badges (scoped to the current user)."""

    permission_classes = [IsAuthenticated, IsFrontendAppUser]

    def get(self, request):
        allowed_ports = user_port_ids(request.user)
        role = user_role(request.user)

        bookings_qs = Booking.objects.all()
        ports_qs = Port.objects.filter(is_active=True)
        if allowed_ports is not None:
            bookings_qs = bookings_qs.filter(port_id__in=allowed_ports)
            ports_qs = ports_qs.filter(id__in=allowed_ports)

        today = timezone.localdate()
        year_bookings = bookings_qs.filter(call_date__year=today.year)

        payload: dict[str, int | None] = {
            "bookings": bookings_qs.count(),
            "reports": year_bookings.count(),
            "ports": ports_qs.count(),
            "shipping_lines": ShippingLine.objects.filter(is_active=True).count(),
            "users": None,
            "report_modules": REPORT_MODULE_COUNT,
        }

        if role == UserRole.ADMIN:
            payload["users"] = (
                User.objects.filter(profile__isnull=False, is_superuser=False).count()
            )

        return Response(payload)
