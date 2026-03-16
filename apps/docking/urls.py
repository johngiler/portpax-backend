"""
URLs del módulo Docking.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import views_metrics

urlpatterns = [
    path("stats/", views.api_docking_stats),
    path("search/", views.api_search),
    path("metrics/scales-by-month/", views_metrics.api_metrics_scales_by_month),
    path("metrics/scales-by-year/", views_metrics.api_metrics_scales_by_year),
    path("metrics/revenue-estimate/", views_metrics.api_metrics_revenue_estimate),
    path("metrics/operations-today/", views_metrics.api_metrics_operations_today),
    path("metrics/berth-timeline/", views_metrics.api_metrics_berth_timeline),
    path("metrics/alerts/", views_metrics.api_metrics_alerts),
]

router = DefaultRouter()
router.register("shipping-lines", views.ShippingLineViewSet, basename="shippingline")
router.register("ports", views.PortViewSet, basename="port")
router.register("berths", views.BerthViewSet, basename="berth")
router.register("ships", views.ShipViewSet, basename="ship")
router.register("scales", views.ScaleViewSet, basename="scale")
router.register("port-fee-rules", views.PortFeeRuleViewSet, basename="portfeerule")

urlpatterns += [
    path("", include(router.urls)),
]
