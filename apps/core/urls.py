from django.urls import path

from apps.core.views import GlobalSearchView, health

urlpatterns = [
    path("health/", health, name="health"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
]
