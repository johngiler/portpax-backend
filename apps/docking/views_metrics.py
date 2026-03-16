"""
Vistas API de métricas para el dashboard (series temporales).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncYear
from rest_framework.decorators import api_view
from rest_framework.response import Response

from datetime import timedelta

from django.utils import timezone

from .models import Berth, PortFeeRule, Scale


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


@api_view(["GET"])
def api_metrics_operations_today(request):
    """
    Indicadores operativos en tiempo real para el día actual (fecha del servidor).
    - ships_in_port_today: barcos distintos con escala hoy
    - scales_today: número de escalas hoy (llegadas)
    - pax_today: PAX desembarcando hoy
    - berths_occupied_today: muelles con al menos una escala hoy
    - total_berths: total de muelles
    - capacity_occupied_pct: % de muelles en uso (0-100)
    """
    today = timezone.now().date()
    scales_today_qs = Scale.objects.filter(date=today)

    scales_today = scales_today_qs.count()
    ships_in_port_today = scales_today_qs.values("ship_id").distinct().count()
    pax_today = scales_today_qs.aggregate(s=Sum("pax_count"))["s"] or 0

    berths_occupied_today = (
        scales_today_qs.filter(berth_id__isnull=False).values("berth_id").distinct().count()
    )
    total_berths = Berth.objects.count()
    capacity_occupied_pct = (
        round(100.0 * berths_occupied_today / total_berths, 1) if total_berths else 0.0
    )

    return Response({
        "date": today.isoformat(),
        "ships_in_port_today": ships_in_port_today,
        "scales_today": scales_today,
        "pax_today": int(pax_today),
        "berths_occupied_today": berths_occupied_today,
        "total_berths": total_berths,
        "capacity_occupied_pct": capacity_occupied_pct,
    })


@api_view(["GET"])
def api_metrics_berth_timeline(request):
    """
    Timeline / Gantt de muelles por día: barcos por muelle y fecha.
    Parámetros: date_from (YYYY-MM-DD), date_to (YYYY-MM-DD). Por defecto hoy + 14 días.
    Devuelve: dates[], berths[] con para cada día las escalas en ese muelle y si hay conflicto.
    """
    today = timezone.now().date()
    try:
        date_from_s = request.GET.get("date_from") or today.isoformat()
        date_to_s = request.GET.get("date_to") or (today + timedelta(days=13)).isoformat()
        date_from = timezone.datetime.strptime(date_from_s, "%Y-%m-%d").date()
        date_to = timezone.datetime.strptime(date_to_s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        date_from = today
        date_to = today + timedelta(days=13)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    # Limitar rango razonable (ej. 60 días)
    if (date_to - date_from).days > 60:
        date_to = date_from + timedelta(days=60)

    dates = []
    d = date_from
    while d <= date_to:
        dates.append(d.isoformat())
        d += timedelta(days=1)

    # Escalas en rango con berth no nulo (para timeline por muelle)
    scales_qs = (
        Scale.objects.filter(
            date__gte=date_from,
            date__lte=date_to,
            berth_id__isnull=False,
        )
        .select_related("ship", "ship__shipping_line", "berth", "berth__port")
        .order_by("date", "berth_id")
    )
    # Agrupar por (berth_id, date)
    by_berth_date = defaultdict(list)
    for s in scales_qs:
        by_berth_date[(s.berth_id, s.date.isoformat())].append(s)

    berths_list = list(
        Berth.objects.select_related("port").order_by("port__name", "name").values("id", "name", "port__name")
    )
    out_berths = []
    for b in berths_list:
        berth_id = b["id"]
        berth_name = b["name"] or f"Muelle {berth_id}"
        port_name = b["port__name"] or "Sin puerto"
        days = []
        for day_str in dates:
            scales_at = by_berth_date.get((berth_id, day_str)) or []
            scale_list = [
                {"scale_id": s.id, "ship_name": s.ship.name, "pax_count": s.pax_count}
                for s in scales_at
            ]
            has_conflict = len(scales_at) > 1
            days.append({
                "date": day_str,
                "scales": scale_list,
                "has_conflict": has_conflict,
            })
        out_berths.append({
            "berth_id": berth_id,
            "berth_name": berth_name,
            "port_name": port_name,
            "days": days,
        })

    return Response({"dates": dates, "berths": out_berths})


@api_view(["GET"])
def api_metrics_alerts(request):
    """
    Alertas operativas para una fecha (por defecto hoy).
    Parámetro: date (YYYY-MM-DD).
    - berth_conflicts: mismo muelle, mismo día, más de una escala.
    - passenger_overflows: escala con pax_count > capacidad (barco o muelle).
    """
    today = timezone.now().date()
    try:
        date_s = request.GET.get("date") or today.isoformat()
        alert_date = timezone.datetime.strptime(date_s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        alert_date = today

    # Conflictos: (berth_id, date) con más de una escala
    scales_with_berth = (
        Scale.objects.filter(date=alert_date, berth_id__isnull=False)
        .select_related("ship", "berth", "berth__port")
        .order_by("berth_id")
    )
    by_berth = defaultdict(list)
    for s in scales_with_berth:
        by_berth[s.berth_id].append(s)

    berth_conflicts = []
    for berth_id, scale_list in by_berth.items():
        if len(scale_list) < 2:
            continue
        first = scale_list[0]
        berth = first.berth
        berth_conflicts.append({
            "date": alert_date.isoformat(),
            "berth_id": berth_id,
            "berth_name": berth.name or f"Muelle {berth_id}",
            "port_name": berth.port.name if berth.port else "Sin puerto",
            "scales": [
                {"scale_id": s.id, "ship_name": s.ship.name}
                for s in scale_list
            ],
        })

    # Exceso de pasajeros: pax_count > capacidad (ship o berth)
    scales_with_pax = (
        Scale.objects.filter(date=alert_date)
        .exclude(pax_count__isnull=True)
        .filter(pax_count__gt=0)
        .select_related("ship", "port", "berth")
    )
    passenger_overflows = []
    for s in scales_with_pax:
        pax = int(s.pax_count)
        capacity = None
        capacity_type = None
        if s.ship_id and s.ship.capacity_pax is not None and s.ship.capacity_pax > 0:
            cap_ship = int(s.ship.capacity_pax)
            if pax > cap_ship:
                capacity = cap_ship
                capacity_type = "ship"
        if capacity is None and s.berth_id and s.berth.capacity_pax is not None and s.berth.capacity_pax > 0:
            cap_berth = int(s.berth.capacity_pax)
            if pax > cap_berth:
                capacity = cap_berth
                capacity_type = "berth"
        if capacity is not None and capacity_type:
            passenger_overflows.append({
                "scale_id": s.id,
                "ship_name": s.ship.name,
                "port_name": s.port.name if s.port else "—",
                "berth_name": s.berth.name if s.berth else "—",
                "date": alert_date.isoformat(),
                "pax_count": pax,
                "capacity": capacity,
                "capacity_type": capacity_type,
            })

    return Response({
        "date": alert_date.isoformat(),
        "berth_conflicts": berth_conflicts,
        "passenger_overflows": passenger_overflows,
    })
