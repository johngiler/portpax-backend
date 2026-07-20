from django.urls import path

from apps.core.views import GlobalSearchView, NavCountsView, health

urlpatterns = [
    path("health/", health, name="health"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path("nav-counts/", NavCountsView.as_view(), name="nav-counts"),
]
