from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalogs.views import (
    BerthImageViewSet,
    BerthViewSet,
    PortBollardViewSet,
    PortImageViewSet,
    PortViewSet,
    PositionImageViewSet,
    PositionViewSet,
    ShippingLineGroupViewSet,
    ShippingLineViewSet,
    VesselViewSet,
)

router = DefaultRouter()
router.register("ports", PortViewSet, basename="port")
router.register("berths", BerthViewSet, basename="berth")
router.register("positions", PositionViewSet, basename="position")
router.register("berth-images", BerthImageViewSet, basename="berth-image")
router.register("port-bollards", PortBollardViewSet, basename="port-bollard")
router.register("port-images", PortImageViewSet, basename="port-image")
router.register("position-images", PositionImageViewSet, basename="position-image")
router.register("shipping-line-groups", ShippingLineGroupViewSet, basename="shipping-line-group")
router.register("shipping-lines", ShippingLineViewSet, basename="shipping-line")
router.register("vessels", VesselViewSet, basename="vessel")

urlpatterns = [
    path("", include(router.urls)),
]
