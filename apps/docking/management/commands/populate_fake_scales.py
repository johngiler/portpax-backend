"""
Añade escalas falsas en todos los puertos para enriquecer gráficas y listas.
No borra datos existentes: usa puertos/ships/berths actuales y crea muelles
donde falten. Genera escalas 2023–2026 con estacionalidad.

Uso:
  python manage.py populate_fake_scales
  python manage.py populate_fake_scales --dry-run
  python manage.py populate_fake_scales --from-year 2024 --scales-per-month 40
"""
from calendar import monthrange
from datetime import date
from random import choice, randint, sample

from django.core.management.base import BaseCommand

from apps.docking.models import Berth, Port, Scale, Ship


# Más actividad en temporada alta (dic, mar, jul)
SEASONAL = {
    1: 1.0, 2: 1.05, 3: 1.2, 4: 1.05, 5: 1.0, 6: 1.1,
    7: 1.25, 8: 1.0, 9: 0.85, 10: 0.9, 11: 1.0, 12: 1.3,
}


class Command(BaseCommand):
    help = "Añade escalas falsas en todos los puertos (2023-2026) para gráficas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo mostrar conteos, no crear")
        parser.add_argument("--from-year", type=int, default=2023, help="Año inicio (default 2023)")
        parser.add_argument("--to-year", type=int, default=2026, help="Año fin (default 2026)")
        parser.add_argument(
            "--scales-per-month",
            type=int,
            default=60,
            help="Escalas totales objetivo por mes (repartidas entre puertos, default 60)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        from_year = options["from_year"]
        to_year = options["to_year"]
        target_per_month = max(10, options["scales_per_month"])

        ports = list(Port.objects.all().order_by("name"))
        if not ports:
            self.stdout.write(self.style.ERROR("No hay puertos. Crea puertos o ejecuta load_port_fees."))
            return

        ships = list(Ship.objects.all()[:80])
        if not ships:
            self.stdout.write(self.style.ERROR("No hay barcos. Importa Ship Master o catálogo."))
            return

        # Asegurar muelles en cada puerto
        port_berths = {}
        created_berths = 0
        for port in ports:
            berths = list(Berth.objects.filter(port=port).order_by("name"))
            if not berths and not dry_run:
                for i in range(1, 4):
                    b = Berth.objects.create(
                        port=port,
                        name=f"Muelle {i}",
                        capacity_pax=randint(2500, 4500),
                        max_length_m=randint(250, 350),
                    )
                    berths.append(b)
                    created_berths += 1
            elif not berths and dry_run:
                berths = []  # en dry-run no hay berth para asignar
            port_berths[port.id] = berths

        today = date.today()
        created = 0
        months_done = 0

        for year in range(from_year, to_year + 1):
            for month in range(1, 13):
                if year == today.year and month > today.month:
                    continue
                _, last_day = monthrange(year, month)
                factor = SEASONAL.get(month, 1.0)
                n_scale = max(10, int(target_per_month * factor))
                port_weights = [randint(1, 3) for _ in ports]
                total_w = sum(port_weights)
                for p_idx, port in enumerate(ports):
                    n_port = max(1, (n_scale * port_weights[p_idx]) // total_w)
                    berth_list = port_berths.get(port.id) or []
                    for _ in range(n_port):
                        day = randint(1, last_day)
                        d = date(year, month, day)
                        ship = choice(ships)
                        berth = choice(berth_list) if berth_list else None
                        base_pax = randint(1200, 4200)
                        pax = max(500, min(6000, int(base_pax * factor)))
                        crew = randint(800, 1200) if randint(0, 1) else None
                        if not dry_run:
                            Scale.objects.create(
                                ship=ship,
                                port=port,
                                berth=berth,
                                date=d,
                                pax_count=pax,
                                crew_count=crew,
                            )
                        created += 1
                months_done += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY-RUN] Se crearían ~{created} escalas en {len(ports)} puertos, "
                    f"{months_done} meses ({from_year}-{to_year})."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Escalas nuevas: {created}. Muelles creados: {created_berths}. "
                    f"Puertos: {len(ports)}, meses: {months_done}."
                )
            )