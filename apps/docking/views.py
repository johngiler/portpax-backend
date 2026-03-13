"""
Vistas API para Docking/Muellaje.
"""
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Berth, Port, Scale, Ship, ShippingLine
from .pagination import DefaultPagination
from .serializers import (
    BerthSerializer,
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
    queryset = Scale.objects.select_related("ship", "port", "berth").all()
    serializer_class = ScaleSerializer
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
