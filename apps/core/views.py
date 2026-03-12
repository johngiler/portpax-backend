"""
Vistas (views) para la API REST.
Separar aquí las vistas por recurso o módulo.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def api_health(request):
    """Comprueba que la API responde. Útil para el frontend y para CI."""
    return Response({"status": "ok", "service": "portpax-api"})
