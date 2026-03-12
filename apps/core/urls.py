"""
URLs del módulo core.
Incluir aquí las rutas de la API de este módulo.
"""
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/", views.api_health),
]
