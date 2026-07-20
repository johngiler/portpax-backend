from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default = True
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        import apps.accounts.signals  # noqa: F401
