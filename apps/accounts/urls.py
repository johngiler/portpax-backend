from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import ManagedUserViewSet, MeChangePasswordView, MeProfileView

router = DefaultRouter()
router.register("users", ManagedUserViewSet, basename="managed-user")

urlpatterns = [
    path("me/", MeProfileView.as_view(), name="me-profile"),
    path("me/change-password/", MeChangePasswordView.as_view(), name="me-change-password"),
    path("", include(router.urls)),
]
