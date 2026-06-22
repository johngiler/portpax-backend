from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bookings.views import BookingViewSet

router = DefaultRouter()
router.register("", BookingViewSet, basename="booking")

urlpatterns = [
    path("", include(router.urls)),
]
