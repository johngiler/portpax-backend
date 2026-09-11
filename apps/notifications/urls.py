from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import NotificationViewSet
from apps.notifications.views_frontend_build import FrontendBuildPublishView

router = DefaultRouter()
router.register("", NotificationViewSet, basename="notification")

urlpatterns = [
    path(
        "frontend-build/",
        FrontendBuildPublishView.as_view(),
        name="frontend-build-publish",
    ),
    path("", include(router.urls)),
]
