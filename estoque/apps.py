from django.apps import AppConfig


class EstoqueConfig(AppConfig):
    """Configuração do aplicativo de saldos e movimentações de estoque."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'estoque'
    verbose_name = 'Controle de Estoque'
