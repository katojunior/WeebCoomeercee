from django.contrib import admin

from cadastro.admin import AUDITORIA_FIELDSET, BaseAdmin
from .models import Cest, Cfop, Ncm


@admin.register(Ncm)
class NcmAdmin(BaseAdmin):
    """Administração de códigos NCM."""

    list_display = ('id', 'codigo', 'descricao', 'aliquota_ipi', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('codigo', 'descricao')
    list_editable = ('ativo',)

    fieldsets = (
        ('Dados do NCM', {
            'fields': (
                ('codigo', 'aliquota_ipi'),
                'descricao',
                'ativo',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(Cest)
class CestAdmin(BaseAdmin):
    """Administração de códigos CEST."""

    list_display = ('id', 'codigo', 'descricao', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('codigo', 'descricao')
    list_editable = ('ativo',)

    fieldsets = (
        ('Dados do CEST', {
            'fields': (
                'codigo',
                'descricao',
                'ativo',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(Cfop)
class CfopAdmin(BaseAdmin):
    """Administração de códigos CFOP."""

    list_display = ('id', 'codigo', 'descricao', 'tipo_operacao', 'movimenta_estoque', 'ativo')
    list_filter = ('ativo', 'tipo_operacao', 'movimenta_estoque')
    search_fields = ('codigo', 'descricao')
    list_editable = ('movimenta_estoque', 'ativo')

    fieldsets = (
        ('Dados do CFOP', {
            'fields': (
                ('codigo', 'tipo_operacao'),
                'descricao',
                ('movimenta_estoque', 'ativo'),
            )
        }),
        AUDITORIA_FIELDSET,
    )
