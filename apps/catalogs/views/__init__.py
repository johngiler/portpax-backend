from apps.catalogs.views.berth import BerthViewSet
from apps.catalogs.views.port import PortViewSet
from apps.catalogs.views.position import PositionViewSet
from apps.catalogs.views.shipping_line import ShippingLineViewSet
from apps.catalogs.views.shipping_line_group import ShippingLineGroupViewSet
from apps.catalogs.views.vessel import VesselViewSet

__all__ = [
    "BerthViewSet",
    "PortViewSet",
    "PositionViewSet",
    "ShippingLineGroupViewSet",
    "ShippingLineViewSet",
    "VesselViewSet",
]
