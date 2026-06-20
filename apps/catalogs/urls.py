from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalogs.views import (
    BerthViewSet,
    PortViewSet,
    PositionViewSet,
    ShippingLineGroupViewSet,
    ShippingLineViewSet,
    VesselViewSet,
)

router = DefaultRouter()
router.register("ports", PortViewSet, basename="port")
router.register("berths", BerthViewSet, basename="berth")
router.register("positions", PositionViewSet, basename="position")
router.register("shipping-line-groups", ShippingLineGroupViewSet, basename="shipping-line-group")
router.register("shipping-lines", ShippingLineViewSet, basename="shipping-line")
router.register("vessels", VesselViewSet, basename="vessel")

urlpatterns = [
    path("", include(router.urls)),
]
