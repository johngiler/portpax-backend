"""
Exporta datos de la BD actual (p. ej. SQLite) a un JSON listo para cargar en PostgreSQL.

Uso (desde el directorio backend, con SQLite como BD por defecto):
    python manage.py export_for_postgres

Genera backend/data/dump_for_postgres.json.

En el servidor con PostgreSQL:
    1. Asegúrate de tener migraciones aplicadas: python manage.py migrate
    2. Copia el archivo dump_for_postgres.json al servidor
    3. python manage.py loaddata dump_for_postgres.json
"""
import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand


OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "dump_for_postgres.json"

# Excluir para que el destino (Postgres) no tenga conflictos y recree lo suyo
EXCLUDE = ["contenttypes", "auth.Permission", "sessions"]


class Command(BaseCommand):
    help = "Exporta datos de la BD actual a un JSON para importar en PostgreSQL (loaddata)."

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            type=str,
            default=str(OUTPUT_FILE),
            help=f"Ruta del archivo de salida (por defecto: {OUTPUT_FILE.name})",
        )

    def handle(self, *args, **options):
        out_path = Path(options["output"]).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Exportando a {out_path} (excluyendo: {', '.join(EXCLUDE)})...")

        with open(out_path, "w", encoding="utf-8") as f:
            call_command(
                "dumpdata",
                "--natural-foreign",
                "--natural-primary",
                "--indent",
                "2",
                *[arg for app in EXCLUDE for arg in ("--exclude", app)],
                stdout=f,
            )

        size = out_path.stat().st_size
        self.stdout.write(self.style.SUCCESS(f"Listo: {out_path} ({size:,} bytes)"))

        self.stdout.write("")
        self.stdout.write("Para cargar en PostgreSQL:")
        self.stdout.write("  1. Copia el archivo al servidor.")
        self.stdout.write("  2. python manage.py migrate   # si hace falta")
        self.stdout.write(f"  3. python manage.py loaddata {out_path.name}")
