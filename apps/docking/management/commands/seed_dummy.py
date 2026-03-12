"""
Comando para poblar datos dummy de Docking/Muellaje.
Uso: python manage.py seed_dummy
Genera datos recientes y también escalas por mes/año (2023-2025) para gráficas.
"""
from datetime import date, timedelta
from random import randint, sample

from django.core.management.base import BaseCommand

from apps.docking.models import Berth, Port, Scale, Ship, ShippingLine


class Command(BaseCommand):
    help = "Crea datos dummy: navieras, puertos, muelles, barcos y escalas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borrar datos existentes de docking antes de crear.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Eliminando datos existentes…")
            Scale.objects.all().delete()
            Ship.objects.all().delete()
            Berth.objects.all().delete()
            Port.objects.all().delete()
            ShippingLine.objects.all().delete()

        if ShippingLine.objects.exists():
            self.stdout.write(self.style.WARNING("Ya hay datos. Usa --clear para reemplazar."))
            return

        # Navieras
        carnival = ShippingLine.objects.create(name="Carnival Cruise Line", code="CCL")
        royal = ShippingLine.objects.create(name="Royal Caribbean", code="RCL")
        norwegian = ShippingLine.objects.create(name="Norwegian Cruise Line", code="NCL")
        msc = ShippingLine.objects.create(name="MSC Cruises", code="MSC")

        # Puertos
        roatan = Port.objects.create(name="Port of Roatán", code="ROA")
        cozumel = Port.objects.create(name="Cozumel", code="CZM")
        belize = Port.objects.create(name="Belize City", code="BZE")

        # Muelles (Roatán)
        roatan_m1 = Berth.objects.create(
            port=roatan, name="Muelle 1", capacity_pax=4000, max_draft_m=10.5, max_length_m=350
        )
        roatan_m2 = Berth.objects.create(
            port=roatan, name="Muelle 2", capacity_pax=3000, max_draft_m=9, max_length_m=280
        )
        roatan_m3 = Berth.objects.create(
            port=roatan, name="Anclaje A", capacity_pax=2000, max_draft_m=8, max_length_m=200
        )
        # Cozumel
        coz_m1 = Berth.objects.create(
            port=cozumel, name="Punta Langosta", capacity_pax=4500, max_draft_m=11, max_length_m=380
        )
        coz_m2 = Berth.objects.create(
            port=cozumel, name="International Pier", capacity_pax=3500, max_draft_m=10, max_length_m=320
        )
        # Belize
        belize_m1 = Berth.objects.create(
            port=belize, name="Tourism Village", capacity_pax=2500, max_draft_m=8.5, max_length_m=260
        )

        # Barcos
        ships_data = [
            (carnival, "Carnival Vista", "96932", 3934, 323, 8.5),
            (carnival, "Carnival Horizon", "97940", 3960, 323, 8.5),
            (royal, "Symphony of the Seas", "9744001", 6680, 362, 9.3),
            (royal, "Allure of the Seas", "9383936", 6296, 360, 9.3),
            (norwegian, "Norwegian Encore", "9751503", 3998, 333, 8.7),
            (norwegian, "Norwegian Bliss", "9751502", 4004, 333, 8.7),
            (msc, "MSC Meraviglia", "9760522", 4500, 315, 8.8),
            (msc, "MSC Seascape", "9788992", 4312, 339, 8.9),
        ]
        ships = []
        for sl, name, imo, pax, length, draft in ships_data:
            s = Ship.objects.create(
                shipping_line=sl,
                name=name,
                imo=imo,
                capacity_pax=pax,
                length_m=length,
                draft_m=draft,
            )
            ships.append(s)

        # Escalas (próximas semanas y algunas pasadas)
        today = date.today()
        berths_roatan = [roatan_m1, roatan_m2, roatan_m3]
        berths_cozumel = [coz_m1, coz_m2]
        berths_belize = [belize_m1]

        scales_config = [
            (0, roatan, berths_roatan, 3200),
            (1, cozumel, berths_cozumel, 2800),
            (2, roatan, berths_roatan, 2900),
            (3, belize, berths_belize, 1800),
            (4, cozumel, berths_cozumel, 4100),
            (5, roatan, berths_roatan, 3500),
            (6, roatan, berths_roatan, 2200),
            (7, cozumel, berths_cozumel, 3900),
        ]

        for ship_idx, port, berth_list, pax in scales_config:
            for week_offset in [-2, -1, 0, 1, 2]:
                d = today + timedelta(days=week_offset * 7 + (ship_idx % 5))
                berth = berth_list[ship_idx % len(berth_list)] if berth_list else None
                Scale.objects.create(
                    ship=ships[ship_idx],
                    port=port,
                    berth=berth,
                    date=d,
                    pax_count=pax,
                )

        # Escalas por mes/año (2023-2025) con variación y estacionalidad para gráficas
        from calendar import monthrange

        # Estacionalidad: más PAX en temporada alta (dic, mar, jul), menos en sep/oct
        seasonal = {
            1: 0.95, 2: 1.0, 3: 1.15, 4: 1.05, 5: 1.0, 6: 1.05,
            7: 1.2, 8: 1.0, 9: 0.85, 10: 0.9, 11: 1.0, 12: 1.25,
        }
        ports = [roatan, cozumel, belize]
        for year in (2023, 2024, 2025):
            for month in range(1, 13):
                if year == 2025 and month > today.month:
                    break
                _, last_day = monthrange(year, month)
                # Variar cantidad de días con escalas por mes (2 a 6)
                num_days = randint(2, 6)
                possible_days = [1, 5, 8, 12, 15, 18, 22, 25]
                chosen_days = sorted(sample(possible_days, min(num_days, len(possible_days))))
                for day in chosen_days:
                    if day > last_day:
                        continue
                    d = date(year, month, day)
                    factor = seasonal.get(month, 1.0)
                    base_pax = randint(1800, 4200)
                    pax = max(800, min(5500, int(base_pax * factor)))
                    for ship_idx in range(len(ships)):
                        port = ports[ship_idx % len(ports)]
                        berth_list = [roatan_m1, roatan_m2, roatan_m3] if port == roatan else ([coz_m1, coz_m2] if port == cozumel else [belize_m1])
                        berth = berth_list[ship_idx % len(berth_list)]
                        # Pequeña variación por barco
                        ship_pax = max(600, pax + randint(-400, 400))
                        Scale.objects.create(
                            ship=ships[ship_idx],
                            port=port,
                            berth=berth,
                            date=d,
                            pax_count=ship_pax,
                        )

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {ShippingLine.objects.count()} navieras, {Port.objects.count()} puertos, "
            f"{Berth.objects.count()} muelles, {Ship.objects.count()} barcos, {Scale.objects.count()} escalas."
        ))
