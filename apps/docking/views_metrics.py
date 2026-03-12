"""
Vistas API de métricas para el dashboard (series temporales).
"""
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncYear
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Scale


@api_view(["GET"])
def api_metrics_scales_by_month(request):
    """
    Escalas y PAX agregados por mes.
    Respuesta: [{"year": 2024, "month": 1, "month_label": "2024-01", "scales": 12, "pax_total": 45000}, ...]
    """
    qs = (
        Scale.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(scales=Count("id"), pax_total=Sum("pax_count"))
        .order_by("month")
    )
    out = []
    for r in qs:
        month = r["month"]
        if month:
            out.append({
                "year": month.year,
                "month": month.month,
                "month_label": month.strftime("%Y-%m"),
                "scales": r["scales"],
                "pax_total": r["pax_total"] or 0,
            })
    return Response(out)


@api_view(["GET"])
def api_metrics_scales_by_year(request):
    """
    Escalas y PAX agregados por año.
    Respuesta: [{"year": 2024, "scales": 120, "pax_total": 450000}, ...]
    """
    qs = (
        Scale.objects.annotate(year=TruncYear("date"))
        .values("year")
        .annotate(scales=Count("id"), pax_total=Sum("pax_count"))
        .order_by("year")
    )
    out = []
    for r in qs:
        y = r["year"]
        if y is not None:
            year_val = y.year if hasattr(y, "year") else int(y)
            out.append({
                "year": year_val,
                "scales": r["scales"],
                "pax_total": r["pax_total"] or 0,
            })
    return Response(out)
