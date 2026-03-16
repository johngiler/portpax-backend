"""
Vistas API de métricas para el dashboard (series temporales).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncYear
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import PortFeeRule, Scale


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


def _build_fee_lookup():
    """Dict (port_id, fee_tier) -> amount_per_pax_usd (Decimal)."""
    rules = PortFeeRule.objects.all().values("port_id", "fee_tier", "amount_per_pax_usd")
    lookup = {}
    for r in rules:
        key = (r["port_id"], r["fee_tier"])
        lookup[key] = Decimal(str(r["amount_per_pax_usd"]))
    return lookup


@api_view(["GET"])
def api_metrics_revenue_estimate(request):
    """
    Estimado de ingresos por muellaje (PAX × tarifa por puerto/tier).
    Devuelve total, por año y por mes (últimos 24 meses útiles).
    """
    fee_lookup = _build_fee_lookup()
    scales = Scale.objects.select_related("ship", "ship__shipping_line", "port").filter(
        pax_count__isnull=False
    ).exclude(pax_count=0)

    by_month = defaultdict(lambda: Decimal("0"))
    by_year = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")

    for s in scales:
        fee_tier = (s.ship.shipping_line.fee_tier or "").strip() or "Others"
        amount = fee_lookup.get((s.port_id, fee_tier)) or fee_lookup.get((s.port_id, "Others"))
        if amount is None:
            continue
        pax = int(s.pax_count or 0)
        rev = amount * pax
        total += rev
        ym = (s.date.year, s.date.month)
        by_month[ym] += rev
        by_year[s.date.year] += rev

    months = sorted(by_month.keys(), reverse=True)[:24]
    month_list = [
        {
            "year": y,
            "month": m,
            "month_label": f"{y}-{m:02d}",
            "estimated_revenue_usd": float(by_month[(y, m)]),
        }
        for (y, m) in reversed(months)
    ]
    year_list = [
        {"year": y, "estimated_revenue_usd": float(by_year[y])}
        for y in sorted(by_year.keys())
    ]

    return Response({
        "total_estimated_revenue_usd": float(total),
        "by_year": year_list,
        "by_month": month_list,
    })
