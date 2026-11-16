from django.contrib import admin, messages
from django.utils import timezone
from .models import Venda, ItemVenda
from financeiro.models import TituloFinanceiro


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


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    autocomplete_fields = ('produto',)
    fields = ('sequencia', 'produto', 'quantidade', 'valor_unitario', 'desconto_unitario', 'valor_total')
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
    """Exibição das parcelas geradas no Financeiro vinculadas à Venda."""
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


@admin.register(Venda)
class VendaAdmin(BaseAdmin):
    list_display = (
        'id', 'cliente', 'status', 'finalizada', 'condicao_pagamento',
        'status_financeiro_badge', 'subtotal', 'desconto', 'valor_total', 'data_venda'
    )
    list_filter = ('finalizada', 'status', 'condicao_pagamento', 'data_venda')
    search_fields = (
        'id', 'cliente__razao_nome', 'cliente__cnpj_cpf',
        'numero_nf', 'numero_cupom_fiscal'
    )
    autocomplete_fields = ('cliente', 'vendedor')
    inlines = [ItemVendaInline, ParcelaReceberInline]
    actions = ['finalizar_e_faturar_vendas', 'reabrir_e_estornar_vendas']
    readonly_fields = (
        'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada',
        'data_finalizacao', 'subtotal', 'valor_total'
    )

    fieldsets = (
        ('Controle e Trava de Fechamento', {
            'fields': (
                ('finalizada', 'data_finalizacao'),
            )
        }),
        ('Identificação da Venda', {
            'fields': (
                ('cliente', 'vendedor'),
                ('status', 'data_venda'),
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
                ('subtotal', 'desconto', 'valor_total'),
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.finalizada and not obj.titulos_financeiros.exists():
            obj.gerar_financeiro(usuario=request.user.username)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.calcular_totais()
        form.instance.save(update_fields=['subtotal', 'valor_total'])
        if form.instance.finalizada and not form.instance.titulos_financeiros.exists():
            form.instance.gerar_financeiro(usuario=request.user.username)

    @admin.action(description="Finalizar e Faturar selecionadas (Gerar Financeiro)")
    def finalizar_e_faturar_vendas(self, request, queryset):
        count = 0
        for venda in queryset.filter(finalizada=False):
            venda.gerar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Venda(s) finalizada(s) e faturada(s) no Financeiro com sucesso.")

    @admin.action(description="Reabrir e Estornar Financeiro selecionadas (Desbloquear)")
    def reabrir_e_estornar_vendas(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir vendas finalizadas.", level=messages.ERROR)
            return
        count = 0
        for venda in queryset.filter(finalizada=True):
            venda.estornar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Venda(s) reaberta(s) e financeiro estornado com sucesso.")


@admin.register(ItemVenda)
class ItemVendaAdmin(BaseAdmin):
    list_display = ('id', 'venda', 'sequencia', 'produto', 'quantidade', 'valor_unitario', 'valor_total')
    list_filter = ('venda__status',)
    search_fields = ('venda__id', 'produto__nome', 'produto__codigo_barras')
    autocomplete_fields = ('venda', 'produto')
