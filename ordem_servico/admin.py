from django.contrib import admin, messages
from django.db import models
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone

from cadastro.models import Pessoas
from financeiro.models import TituloFinanceiro
from .models import EquipamentoCliente, OrdemServico, ItemOrdemServico


AUDITORIA_FIELDSET = (
    'Auditoria e Configuração',
    {
        'classes': ('collapse',),
        'fields': (
            ('usuario', 'usuario_atualizou'),
            ('data_hora', 'data_hora_atualizada'),
        ),
    },
)


class BaseAdmin(admin.ModelAdmin):
    """Classe base do Admin para preenchimento e controle automático dos campos de auditoria."""
    readonly_fields = ('usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada')

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.usuario and request.user.is_authenticated:
                obj.usuario = request.user.username
        else:
            if request.user.is_authenticated:
                obj.usuario_atualizou = request.user.username
        super().save_model(request, obj, form, change)


class ItemOrdemServicoInline(admin.TabularInline):
    model = ItemOrdemServico
    extra = 0
    autocomplete_fields = ('produto',)
    fields = ('tipo_item', 'produto', 'descricao_personalizada', 'quantidade', 'valor_unitario', 'valor_total')
    readonly_fields = ('valor_total',)

    def has_add_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_delete_permission(request, obj)


class ParcelaReceberInline(admin.TabularInline):
    """Exibição das parcelas geradas no Financeiro vinculadas à Ordem de Serviço."""
    model = TituloFinanceiro
    extra = 0
    can_delete = False
    verbose_name = 'Parcela / Título a Receber'
    verbose_name_plural = 'Parcelas Geradas (Financeiro)'
    fields = (
        'parcela_numero',
        'parcela_total',
        'data_vencimento',
        'valor_original',
        'valor_pago',
        'saldo_devedor',
        'status',
        'forma_pagamento_prevista',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EquipamentoCliente)
class EquipamentoClienteAdmin(BaseAdmin):
    list_display = ('id', 'descricao', 'cliente', 'marca', 'modelo', 'numero_serie', 'ativo')
    list_filter = ('ativo', 'marca')
    search_fields = ('descricao', 'modelo', 'numero_serie', 'cliente__razao_nome', 'cliente__cnpj_cpf')
    autocomplete_fields = ('cliente', 'marca')

    fieldsets = (
        ('Identificação do Equipamento', {
            'fields': (
                'cliente',
                'descricao',
                ('marca', 'modelo'),
                'numero_serie',
                'ativo',
            )
        }),
        ('Observações', {
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(OrdemServico)
class OrdemServicoAdmin(BaseAdmin):
    list_display = (
        'id', 'cliente', 'equipamento', 'tecnico', 'status',
        'finalizada', 'condicao_pagamento', 'status_financeiro_badge',
        'data_abertura', 'data_conclusao', 'valor_total'
    )
    list_filter = ('finalizada', 'status', 'condicao_pagamento', 'data_abertura', 'data_conclusao', 'tecnico')
    search_fields = (
        'id', 'cliente__razao_nome', 'cliente__cnpj_cpf',
        'equipamento__descricao', 'equipamento__numero_serie',
        'numero_nf', 'numero_cupom_fiscal'
    )
    autocomplete_fields = ('cliente',)
    inlines = [ItemOrdemServicoInline, ParcelaReceberInline]
    actions = ['finalizar_e_faturar_ordens', 'reabrir_e_estornar_ordens']
    readonly_fields = (
        'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada',
        'data_finalizacao', 'valor_pecas', 'valor_servicos', 'valor_total'
    )

    class Media:
        js = ('ordem_servico/js/os_admin.js',)

    fieldsets = (
        ('Controle e Trava de Fechamento', {
            'fields': (
                ('finalizada', 'data_finalizacao'),
            )
        }),
        ('Informações da Ordem de Serviço', {
            'fields': (
                ('cliente', 'equipamento'),
                ('tecnico', 'status'),
                ('data_abertura', 'previsao_entrega', 'data_conclusao'),
            )
        }),
        ('Diagnóstico e Laudo Técnico', {
            'fields': (
                'defeito_reclamado',
                'laudo_tecnico',
            )
        }),
        ('Condições de Pagamento e Faturamento', {
            'fields': (
                ('condicao_pagamento', 'conta_destino'),
                ('data_primeiro_vencimento', 'numero_parcelas', 'intervalo_dias'),
                ('numero_nf', 'numero_cupom_fiscal'),
            )
        }),
        ('Valores e Totais', {
            'fields': (
                ('valor_pecas', 'valor_servicos'),
                ('desconto', 'valor_total'),
            )
        }),
        ('Observações', {
            'classes': ('collapse',),
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Financeiro')
    def status_financeiro_badge(self, obj):
        return obj.status_financeiro

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.finalizada:
            # Trava 100% dos campos em modo somente leitura
            return [f.name for f in obj._meta.fields]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        if obj and obj.finalizada and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'tecnico':
            # Lista apenas funcionários. Se estiver editando uma OS existente cujo técnico histórico
            # não está marcado como funcionário, inclui-o para preservar o histórico.
            object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
            qs = Pessoas.objects.filter(funcionario=True)
            if object_id:
                os_obj = OrdemServico.objects.filter(pk=object_id).first()
                if os_obj and os_obj.tecnico_id:
                    qs = Pessoas.objects.filter(models.Q(funcionario=True) | models.Q(pk=os_obj.tecnico_id))
            kwargs['queryset'] = qs.order_by('razao_nome')

        elif db_field.name == 'equipamento':
            # Filtra apenas os equipamentos do cliente selecionado
            cliente_id = None
            if request:
                if request.method == 'POST':
                    cliente_id = request.POST.get('cliente')
                elif request.resolver_match and 'object_id' in request.resolver_match.kwargs:
                    os_obj = OrdemServico.objects.filter(pk=request.resolver_match.kwargs['object_id']).first()
                    if os_obj and os_obj.cliente_id:
                        cliente_id = os_obj.cliente_id

            if cliente_id:
                kwargs['queryset'] = EquipamentoCliente.objects.filter(
                    cliente_id=cliente_id,
                    ativo=True
                ).order_by('descricao')
            else:
                if request and request.method == 'POST':
                    kwargs['queryset'] = EquipamentoCliente.objects.filter(ativo=True)
                else:
                    kwargs['queryset'] = EquipamentoCliente.objects.none()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.recalcular_totais(salvar=True)
        if obj.finalizada and not obj.titulos_financeiros.exists():
            obj.gerar_financeiro(usuario=request.user.username)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalcular_totais(salvar=True)
        if form.instance.finalizada and not form.instance.titulos_financeiros.exists():
            form.instance.gerar_financeiro(usuario=request.user.username)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'equipamentos-cliente/<int:cliente_id>/',
                self.admin_site.admin_view(self.get_equipamentos_cliente),
                name='ordem_servico_equipamentos_cliente',
            ),
        ]
        return custom_urls + urls

    def get_equipamentos_cliente(self, request, cliente_id):
        equipamentos = EquipamentoCliente.objects.filter(
            cliente_id=cliente_id,
            ativo=True
        ).order_by('descricao')
        dados = [{'id': eq.id, 'descricao': str(eq)} for eq in equipamentos]
        return JsonResponse({'equipamentos': dados})

    @admin.action(description="Finalizar e Faturar selecionadas (Gerar Financeiro)")
    def finalizar_e_faturar_ordens(self, request, queryset):
        count = 0
        for ordem in queryset.filter(finalizada=False):
            ordem.gerar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Ordem(ns) de Serviço finalizada(s) e faturada(s) no Financeiro com sucesso.")

    @admin.action(description="Reabrir e Estornar Financeiro selecionadas (Desbloquear)")
    def reabrir_e_estornar_ordens(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir ordens de serviço finalizadas.", level=messages.ERROR)
            return
        count = 0
        for ordem in queryset.filter(finalizada=True):
            ordem.estornar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Ordem(ns) de Serviço reaberta(s) e financeiro estornado com sucesso.")


@admin.register(ItemOrdemServico)
class ItemOrdemServicoAdmin(BaseAdmin):
    list_display = ('id', 'ordem', 'tipo_item', 'produto', 'quantidade', 'valor_unitario', 'valor_total')
    list_filter = ('tipo_item',)
    search_fields = ('ordem__id', 'produto__nome', 'descricao_personalizada')
    autocomplete_fields = ('ordem', 'produto', 'equipamento')
