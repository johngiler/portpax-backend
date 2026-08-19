from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalogs.views import (
    BerthImageViewSet,
    BerthViewSet,
    PortBollardViewSet,
    PortFenderViewSet,
    PortImageViewSet,
    PortViewSet,
    PositionImageViewSet,
    PositionLoaRecalcRuleViewSet,
    PositionNestingRuleViewSet,
    PositionViewSet,
    ShippingLineGroupViewSet,
    ShippingLineViewSet,
    VesselViewSet,
    PortProximityViewSet,
)

router = DefaultRouter()
router.register("ports", PortViewSet, basename="port")
router.register("berths", BerthViewSet, basename="berth")
router.register("positions", PositionViewSet, basename="position")
router.register(
    "position-nesting-rules",
    PositionNestingRuleViewSet,
    basename="position-nesting-rule",
)
router.register(
    "position-loa-recalc-rules",
    PositionLoaRecalcRuleViewSet,
    basename="position-loa-recalc-rule",
)
router.register("berth-images", BerthImageViewSet, basename="berth-image")
router.register("port-bollards", PortBollardViewSet, basename="port-bollard")
router.register("port-fenders", PortFenderViewSet, basename="port-fender")
router.register("port-images", PortImageViewSet, basename="port-image")
router.register("position-images", PositionImageViewSet, basename="position-image")
router.register("shipping-line-groups", ShippingLineGroupViewSet, basename="shipping-line-group")
router.register("shipping-lines", ShippingLineViewSet, basename="shipping-line")
router.register("vessels", VesselViewSet, basename="vessel")
router.register(
    "port-proximities",
    PortProximityViewSet,
    basename="port-proximity",
)

urlpatterns = [
    path("", include(router.urls)),
]
