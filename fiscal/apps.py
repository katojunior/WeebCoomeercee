from django.apps import AppConfig


class FiscalConfig(AppConfig):
    """Configuração do aplicativo de tabelas de referência fiscal."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fiscal'
    verbose_name = 'Tabelas Fiscais'
