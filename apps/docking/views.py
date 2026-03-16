"""
Vistas API para Docking/Muellaje.
"""
from datetime import datetime as dt_parse

from django.db.models import Q

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Berth, Port, PortFeeRule, Scale, Ship, ShippingLine
from .pagination import DefaultPagination
from .serializers import (
    BerthSerializer,
    PortFeeRuleSerializer,
    PortSerializer,
    ScaleSerializer,
    ShipSerializer,
    ShippingLineSerializer,
)


class ShippingLineViewSet(viewsets.ModelViewSet):
    queryset = ShippingLine.objects.all()
    serializer_class = ShippingLineSerializer
    pagination_class = DefaultPagination


class PortViewSet(viewsets.ModelViewSet):
    queryset = Port.objects.all()
    serializer_class = PortSerializer
    pagination_class = DefaultPagination


class BerthViewSet(viewsets.ModelViewSet):
    queryset = Berth.objects.select_related("port").all()
    serializer_class = BerthSerializer
    pagination_class = DefaultPagination


class ShipViewSet(viewsets.ModelViewSet):
    queryset = Ship.objects.select_related("shipping_line").all()
    serializer_class = ShipSerializer
    pagination_class = DefaultPagination


class ScaleViewSet(viewsets.ModelViewSet):
    serializer_class = ScaleSerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        qs = Scale.objects.select_related(
            "ship", "ship__shipping_line", "port", "berth"
        ).all()
        date_after = self.request.query_params.get("date_after")
        date_before = self.request.query_params.get("date_before")
        if date_after:
            try:
                d = dt_parse.strptime(date_after, "%Y-%m-%d").date()
                qs = qs.filter(date__gte=d)
            except (ValueError, TypeError):
                pass
        if date_before:
            try:
                d = dt_parse.strptime(date_before, "%Y-%m-%d").date()
                qs = qs.filter(date__lte=d)
            except (ValueError, TypeError):
                pass
        return qs.order_by("-date", "port", "ship")


class PortFeeRuleViewSet(viewsets.ModelViewSet):
    queryset = PortFeeRule.objects.select_related("port").all()
    serializer_class = PortFeeRuleSerializer
    pagination_class = DefaultPagination


@api_view(["GET"])
def api_docking_stats(request):
    """Resumen para el dashboard: conteos de navieras, puertos, muelles, barcos, escalas."""
    return Response({
        "shipping_lines": ShippingLine.objects.count(),
        "ports": Port.objects.count(),
        "berths": Berth.objects.count(),
        "ships": Ship.objects.count(),
        "scales": Scale.objects.count(),
    })


@api_view(["GET"])
def api_search(request):
    """
    Buscador global: barco, naviera, puerto, escala.
    Parámetro: q (mínimo 2 caracteres). Devuelve hasta 5 resultados por tipo.
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return Response({
            "shipping_lines": [],
            "ports": [],
            "ships": [],
            "scales": [],
        })

    # Navieras: name, code
    shipping_lines = list(
        ShippingLine.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q)
        ).values("id", "name", "code")[:5]
    )
    # Puertos: name, code
    ports = list(
        Port.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q)
        ).values("id", "name", "code")[:5]
    )
    # Barcos: name, code, imo
    ships = list(
        Ship.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(imo__icontains=q)
        ).select_related("shipping_line").values("id", "name", "code", "shipping_line__name")[:5]
    )
    ships = [
        {
            "id": s["id"],
            "name": s["name"],
            "code": s["code"],
            "shipping_line_name": s["shipping_line__name"],
        }
        for s in ships
    ]
    # Escalas: por ship name o port name
    scales = list(
        Scale.objects.filter(
            Q(ship__name__icontains=q) | Q(port__name__icontains=q)
        )
        .select_related("ship", "port")
        .order_by("-date")[:5]
        .values("id", "date", "ship__name", "port__name")
    )
    scales = [
        {
            "id": s["id"],
            "date": s["date"].isoformat() if s["date"] else None,
            "ship_name": s["ship__name"],
            "port_name": s["port__name"],
        }
        for s in scales
    ]

    return Response({
        "shipping_lines": shipping_lines,
        "ports": ports,
        "ships": ships,
        "scales": scales,
    })
