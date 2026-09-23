from django.apps import AppConfig


class LegacyImportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "legacy_import"
    verbose_name = "Перенос данных из старой системы"
