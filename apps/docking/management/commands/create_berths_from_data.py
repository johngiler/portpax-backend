"""
Crea muelles (Berth) a partir de las escalas existentes y asigna cada escala a un muelle.

Para cada puerto que tiene escalas:
- Calcula el máximo de escalas en un mismo día → número de muelles a crear.
- Crea Muelle 1, Muelle 2, ... con capacidad derivada de los barcos que visitan el puerto.
- Asigna cada escala a un muelle (mismo día mismo puerto → reparto en orden).

Uso:
  python manage.py create_berths_from_data
  python manage.py create_berths_from_data --dry-run
  python manage.py create_berths_from_data --min-berths 2   # mínimo de muelles por puerto
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, Max

from apps.docking.models import Berth, Port, Scale, Ship


class Command(BaseCommand):
    help = "Crea muelles por puerto según escalas existentes y asigna cada escala a un muelle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo mostrar qué se haría, sin crear ni actualizar.",
        )
        parser.add_argument(
            "--min-berths",
            type=int,
            default=1,
            help="Mínimo de muelles a crear por puerto (default: 1).",
        )
        parser.add_argument(
            "--skip-assign",
            action="store_true",
            help="Solo crear muelles, no asignar escalas a muelles.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        min_berths = max(1, options["min_berths"])
        skip_assign = options["skip_assign"]

        # Puertos que tienen escalas
        port_ids_with_scales = Scale.objects.values_list("port_id", flat=True).distinct()
        ports = list(Port.objects.filter(id__in=port_ids_with_scales).order_by("name"))

        if not ports:
            self.stdout.write(self.style.WARNING("No hay puertos con escalas. Nada que hacer."))
            return

        # Por puerto: máximo de escalas en un mismo día
        daily_counts = (
            Scale.objects.values("port_id", "date")
            .annotate(cnt=Count("id"))
            .order_by("port_id", "date")
        )
        port_max_per_day = defaultdict(int)
        for row in daily_counts:
            port_max_per_day[row["port_id"]] = max(port_max_per_day[row["port_id"]], row["cnt"])

        created_berths = 0
        assigned_scales = 0

        for port in ports:
            n = max(port_max_per_day.get(port.id, 0), min_berths)

            # Capacidad del muelle: máximo length_m y capacity_pax de barcos que visitan este puerto
            ship_ids = Scale.objects.filter(port=port).values_list("ship_id", flat=True).distinct()
            agg = Ship.objects.filter(id__in=ship_ids).aggregate(
                max_length=Max("length_m"),
                max_pax=Max("capacity_pax"),
            )
            max_length_m = agg["max_length"]
            capacity_pax = agg["max_pax"] if agg["max_pax"] is not None else None

            existing = list(Berth.objects.filter(port=port).order_by("name"))
            to_create = n - len(existing)

            if to_create <= 0 and not skip_assign:
                berths = existing[:n]
            else:
                berths = list(existing)
                for i in range(to_create):
                    name = f"Muelle {len(berths) + 1}"
                    if dry_run:
                        self.stdout.write(f"  [DRY-RUN] Crear muelle: {port.name} — {name}")
                    else:
                        b = Berth.objects.create(
                            port=port,
                            name=name,
                            capacity_pax=capacity_pax,
                            max_length_m=max_length_m,
                        )
                        berths.append(b)
                        created_berths += 1

            if skip_assign:
                continue

            if dry_run:
                scales_at_port = Scale.objects.filter(port=port).count()
                assigned_scales += scales_at_port
                self.stdout.write(
                    f"  [DRY-RUN] {port.name}: {n} muelle(s), asignar {scales_at_port} escalas."
                )
                continue

            # Asignar escalas a muelles (por fecha, luego por barco)
            berth_list = [b for b in berths[:n] if b is not None]
            assigned = self._assign_scales_to_berths(port, berth_list, dry_run=False)
            assigned_scales += assigned

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Muelles creados: {created_berths}. Escalas asignadas a muelle: {assigned_scales}."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"[DRY-RUN] Se crearían muelles y se asignarían {assigned_scales} escalas.")
            )

    def _assign_scales_to_berths(self, port, berths, dry_run=False):
        """Asigna cada escala del puerto a un muelle (mismo día → reparto en orden)."""
        if not berths:
            return 0
        berth_list = [b for b in berths if b is not None]
        if not berth_list:
            return 0

        scales_by_date = (
            Scale.objects.filter(port=port, berth__isnull=True)
            .order_by("date", "ship__name")
            .select_related("ship")
        )
        # Agrupar por (date) y asignar en orden
        by_date = defaultdict(list)
        for s in scales_by_date:
            by_date[s.date].append(s)

        updated = 0
        for date, scale_list in sorted(by_date.items()):
            for i, scale in enumerate(scale_list):
                berth = berth_list[i % len(berth_list)]
                if berth and not dry_run:
                    scale.berth = berth
                    scale.save(update_fields=["berth"])
                    updated += 1
        return updated
