from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.accounts.permissions import (
    IsFrontendAppUser,
    user_port_ids,
    user_role,
)
from apps.bookings.models import Booking
from apps.catalogs.models import Port, ShippingLine, Vessel

_LIMIT = 6
_MIN_QUERY = 2


class GlobalSearchView(APIView):
    """Cross-domain search: ports, shipping lines, vessels, bookings."""

    permission_classes = [IsAuthenticated, IsFrontendAppUser]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < _MIN_QUERY:
            return Response(_empty())

        role = user_role(request.user)
        include_catalogs = role in {UserRole.ADMIN, UserRole.VIEWER}
        allowed_ports = user_port_ids(request.user)

        payload = _empty()
        if include_catalogs:
            payload["ports"] = _search_ports(q, allowed_ports)
            payload["shipping_lines"] = _search_shipping_lines(q)
            payload["ships"] = _search_vessels(q)
        payload["scales"] = _search_bookings(q, allowed_ports)
        return Response(payload)


def _empty() -> dict:
    return {
        "ports": [],
        "shipping_lines": [],
        "ships": [],
        "scales": [],
    }


def _search_ports(q: str, allowed_ports: set[int] | None) -> list[dict]:
    qs = Port.objects.filter(
        Q(code__icontains=q)
        | Q(name__icontains=q)
        | Q(commercial_name__icontains=q)
    ).order_by("name")
    if allowed_ports is not None:
        qs = qs.filter(id__in=allowed_ports)
    return [
        {"id": p.id, "name": p.name, "code": p.code}
        for p in qs[:_LIMIT]
    ]


def _search_shipping_lines(q: str) -> list[dict]:
    qs = (
        ShippingLine.objects.filter(
            Q(code__icontains=q) | Q(name__icontains=q) | Q(group__name__icontains=q)
        )
        .select_related("group")
        .order_by("name")[:_LIMIT]
    )
    return [{"id": line.id, "name": line.name, "code": line.code} for line in qs]


def _search_vessels(q: str) -> list[dict]:
    qs = (
        Vessel.objects.filter(
            Q(name__icontains=q)
            | Q(vessel_class__icontains=q)
            | Q(shipping_line__name__icontains=q)
        )
        .select_related("shipping_line")
        .order_by("name")[:_LIMIT]
    )
    return [
        {
            "id": vessel.id,
            "name": vessel.name,
            "shipping_line_name": vessel.shipping_line.name,
            "shipping_line_code": vessel.shipping_line.code,
        }
        for vessel in qs
    ]


def _search_bookings(q: str, allowed_ports: set[int] | None) -> list[dict]:
    qs = Booking.objects.filter(
        Q(booking_code__icontains=q)
        | Q(vessel__name__icontains=q)
        | Q(port__name__icontains=q)
        | Q(port__code__icontains=q)
        | Q(shipping_line__name__icontains=q)
    ).select_related("vessel", "port").order_by("-call_date", "-id")
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    return [
        {
            "id": booking.id,
            "booking_code": booking.booking_code,
            "date": booking.call_date.isoformat() if booking.call_date else None,
            "ship_name": booking.vessel.name,
            "port_name": booking.port.name,
        }
        for booking in qs[:_LIMIT]
    ]
