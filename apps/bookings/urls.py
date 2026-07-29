from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bookings.views import BookingViewSet, LongTermAgreementViewSet

router = DefaultRouter()
router.register(
    "long-term-agreements",
    LongTermAgreementViewSet,
    basename="long-term-agreement",
)
router.register("", BookingViewSet, basename="booking")

urlpatterns = [
    path("", include(router.urls)),
]
