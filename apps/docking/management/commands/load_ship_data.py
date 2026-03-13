"""
Importa datos desde:
1) Cruise Ship Master (SHIP DB.csv): navieras (BRAND) y barcos (SHIP NAME, LOA, PAX).
2) Barcos recibidos P.O.R. (Sheet1.csv): escalas con fecha, barco, pasajeros, tripulantes.

Uso:
  python manage.py load_ship_data /ruta/al/SHIP_DB.csv /ruta/a/Barcos_recibidos.csv

Si solo quieres cargar uno:
  python manage.py load_ship_data --ships-only /ruta/SHIP_DB.csv
  python manage.py load_ship_data --scales-only /ruta/Barcos_recibidos.csv
"""
import csv
import re
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.docking.models import Port, Scale, Ship, ShippingLine

# Meses en español e inglés para parsear fechas
MONTHES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "deciembre": 12,
}
MONTHES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_int_or_null(s):
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip().replace(",", "").replace(" ", "")
    try:
        return int(s)
    except ValueError:
        return None


def parse_decimal_or_null(s):
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip().replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def parse_date_es_en(s):
    """Parsea fechas como '1 de December de 2017' o '26 de deciembre de 2017'."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    # "1 de December de 2017" -> day=1, month=12, year=2017
    m = re.match(r"(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})", s, re.IGNORECASE)
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).lower()
    year = int(m.group(3))
    month = MONTHES_ES.get(month_name) or MONTHES_EN.get(month_name)
    if not month:
        return None
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def normalize_ship_name(name):
    """Normaliza nombre de barco para matching: mayúsculas, sin espacios extra."""
    if not name:
        return ""
    return " ".join(str(name).strip().upper().split())


class Command(BaseCommand):
    help = "Importa navieras, barcos y escalas desde CSV (Ship Master + Barcos recibidos P.O.R.)."

    def add_arguments(self, parser):
        parser.add_argument(
            "ship_csv",
            nargs="?",
            help="Ruta al CSV Cruise Ship Master (SHIP DB.csv).",
        )
        parser.add_argument(
            "scales_csv",
            nargs="?",
            help="Ruta al CSV Barcos recibidos P.O.R. (Sheet1.csv).",
        )
        parser.add_argument(
            "--ships-only",
            action="store_true",
            help="Solo cargar Ship Master (requiere ship_csv).",
        )
        parser.add_argument(
            "--scales-only",
            action="store_true",
            help="Solo cargar escalas P.O.R. (requiere scales_csv).",
        )
        parser.add_argument(
            "--port-code",
            default="POR",
            help="Código del puerto para las escalas (default: POR).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No guardar en DB, solo mostrar qué se importaría.",
        )

    def handle(self, *args, **options):
        ship_csv = options.get("ship_csv")
        scales_csv = options.get("scales_csv")
        ships_only = options.get("ships_only")
        scales_only = options.get("scales_only")
        port_code = options.get("port_code")
        dry_run = options.get("dry_run")

        if ships_only:
            if not ship_csv:
                self.stdout.write(self.style.ERROR("Con --ships-only indica ship_csv."))
                return
            self.run_ship_master(ship_csv, dry_run)
            return
        if scales_only:
            if not scales_csv:
                self.stdout.write(self.style.ERROR("Con --scales-only indica scales_csv."))
                return
            self.run_scales_por(scales_csv, port_code, dry_run)
            return
        if not ship_csv or not scales_csv:
            self.stdout.write(
                self.style.ERROR("Indica ambos CSV o usa --ships-only / --scales-only con un archivo.")
            )
            return

        self.run_ship_master(ship_csv, dry_run)
        self.run_scales_por(scales_csv, port_code, dry_run)

    def run_ship_master(self, path, dry_run):
        """Carga Cruise Ship Master: BRAND -> ShippingLine, SHIP NAME + LOA + PAX -> Ship."""
        self.stdout.write(f"Cargando Ship Master: {path}")
        created_lines = 0
        created_ships = 0

        try:
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Archivo no encontrado: {path}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        # Buscar fila de cabecera (SHIP NAME, BRAND, ...)
        header_idx = None
        for i, row in enumerate(rows):
            if len(row) > 8 and "SHIP" in str(row[2]).upper() and "BRAND" in str(row[3]).upper():
                header_idx = i
                break
        if header_idx is None:
            self.stdout.write(self.style.ERROR("No se encontró cabecera SHIP NAME / BRAND en el CSV."))
            return

        for row in rows[header_idx + 1 :]:
            if len(row) < 9:
                continue
            ship_name = (row[2] or "").strip()
            brand = (row[3] or "").strip()
            loa = parse_decimal_or_null(row[7] if len(row) > 7 else None)
            pax = parse_int_or_null(row[8] if len(row) > 8 else None)
            if not ship_name:
                continue
            if not brand:
                brand = "Otros"

            if dry_run:
                created_lines += 1
                created_ships += 1
                continue

            line, _ = ShippingLine.objects.get_or_create(
                name=brand,
                defaults={"code": brand[:20].upper().replace(" ", "")},
            )
            if _:
                created_lines += 1

            _, created = Ship.objects.get_or_create(
                shipping_line=line,
                name=ship_name,
                defaults={
                    "capacity_pax": pax,
                    "length_m": loa,
                },
            )
            if created:
                created_ships += 1

        self.stdout.write(self.style.SUCCESS(f"Ship Master: {created_lines} navieras nuevas, {created_ships} barcos nuevos."))

    def run_scales_por(self, path, port_code, dry_run):
        """Carga Barcos recibidos P.O.R.: crea puerto POR si no existe y escalas (barco, fecha, pax, crew)."""
        self.stdout.write(f"Cargando escalas P.O.R.: {path}")

        try:
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Archivo no encontrado: {path}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        # Cabecera en fila 1: Posicion, Cantidad..., Fecha Servicio, Barco, Pasajeros, Tripulantes
        header_idx = None
        for i, row in enumerate(rows):
            if len(row) > 5 and "Barco" in str(row[4]) and "Fecha" in str(row[3]):
                header_idx = i
                break
        if header_idx is None:
            self.stdout.write(self.style.ERROR("No se encontró cabecera Barco / Fecha Servicio en el CSV."))
            return

        if not dry_run:
            port, _ = Port.objects.get_or_create(
                code=port_code,
                defaults={"name": f"P.O.R. ({port_code})"},
            )
            if _:
                self.stdout.write(f"Puerto creado: {port.name}")
            # Naviera por defecto para barcos que no estén en el Ship Master
            default_line, _ = ShippingLine.objects.get_or_create(
                name="P.O.R. (importación)",
                defaults={"code": "POR-IMP"},
            )
        else:
            port = None
            default_line = None

        created_scales = 0
        created_ships = 0
        name_to_ship = {}  # normalize_ship_name -> Ship (para no repetir lookups)

        for row in rows[header_idx + 1 :]:
            if len(row) < 7:
                continue
            date_str = (row[3] or "").strip()
            ship_name_raw = (row[4] or "").strip()
            pax = parse_int_or_null(row[5])
            crew = parse_int_or_null(row[6])
            if not ship_name_raw:
                continue
            d = parse_date_es_en(date_str)
            if not d:
                continue

            if dry_run:
                created_scales += 1
                continue

            key = normalize_ship_name(ship_name_raw)
            if key not in name_to_ship:
                ship = Ship.objects.filter(name__iexact=ship_name_raw).first()
                if not ship:
                    for s in Ship.objects.all():
                        if normalize_ship_name(s.name) == key:
                            ship = s
                            break
                if not ship:
                    ship = Ship.objects.create(
                        shipping_line=default_line,
                        name=ship_name_raw,
                        capacity_pax=pax,
                    )
                    created_ships += 1
                name_to_ship[key] = ship

            ship = name_to_ship[key]
            Scale.objects.create(
                ship=ship,
                port=port,
                date=d,
                pax_count=pax,
                crew_count=crew,
            )
            created_scales += 1

        self.stdout.write(self.style.SUCCESS(f"Escalas P.O.R.: {created_ships} barcos nuevos, {created_scales} escalas creadas."))
