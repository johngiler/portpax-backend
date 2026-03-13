"""
Crea o actualiza el usuario por defecto: admin / Abc1234
Uso: python manage.py create_default_user
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Abc1234"


class Command(BaseCommand):
    help = "Crea o actualiza el usuario por defecto (admin / Abc1234)"

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=DEFAULT_USERNAME,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if not created:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
        user.set_password(DEFAULT_PASSWORD)
        user.save(update_fields=["password"])
        action = "Creado" if created else "Actualizado"
        self.stdout.write(
            self.style.SUCCESS(f"{action} usuario '{DEFAULT_USERNAME}' con contraseña configurada.")
        )
