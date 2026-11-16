from decimal import Decimal
from django.contrib import admin
from django.db.models import Sum

from .models import Estado, Cidade, Pessoas
from ordem_servico.models import EquipamentoCliente, OrdemServico
from vendas.models import Venda
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


@admin.register(Estado)
class EstadoAdmin(BaseAdmin):
    list_display = ('id', 'codigoUf', 'uf', 'estado', 'regiao')
    search_fields = ('uf', 'estado', 'codigoUf')
    list_filter = ('regiao',)

    fieldsets = (
        ('Identificação do Estado', {
            'fields': (
                ('codigoUf', 'uf'),
                'estado',
                'regiao',
            )
        }),
        ('Coordenadas Geográficas', {
            'classes': ('collapse',),
            'fields': (
                ('latitude', 'longitude'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(Cidade)
class CidadeAdmin(BaseAdmin):
    list_display = ('id', 'descricaoCidade', 'uf', 'capital', 'ddd', 'codigoIbge')
    search_fields = ('descricaoCidade', 'descricao_completa', 'codigoIbge')
    list_filter = ('uf', 'capital')
    list_editable = ('capital',)
    readonly_fields = ('descricao_completa', 'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada')

    fieldsets = (
        ('Identificação da Cidade', {
            'fields': (
                'descricaoCidade',
                'uf',
                ('capital', 'ddd'),
                'codigoIbge',
                'descricao_completa',
            )
        }),
        ('Localização e Fuso Horário', {
            'classes': ('collapse',),
            'fields': (
                'fusoHorario',
                ('latitude', 'longitude'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


class EquipamentoClienteInline(admin.TabularInline):
    model = EquipamentoCliente
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    autocomplete_fields = ('marca',)
    fields = ('descricao', 'marca', 'modelo', 'numero_serie', 'ativo')
    show_change_link = True
    verbose_name = 'Equipamento'
    verbose_name_plural = 'Equipamentos do Cliente'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('marca')


class VendaClienteInline(admin.TabularInline):
    model = Venda
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'data_venda',
        'vendedor',
        'status',
        'finalizada',
        'condicao_pagamento',
        'subtotal',
        'desconto',
        'valor_total',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Venda'
    verbose_name_plural = 'Histórico de Vendas (Últimas 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('vendedor').order_by('-data_venda', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(Venda.objects.filter(cliente_id=object_id).order_by('-data_venda', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


class OrdemServicoClienteInline(admin.TabularInline):
    model = OrdemServico
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'data_abertura',
        'equipamento',
        'tecnico',
        'status',
        'finalizada',
        'condicao_pagamento',
        'valor_total',
        'data_conclusao',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Ordem de Serviço'
    verbose_name_plural = 'Histórico de Ordens de Serviço (Últimas 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('equipamento', 'tecnico').order_by('-data_abertura', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(OrdemServico.objects.filter(cliente_id=object_id).order_by('-data_abertura', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


class TituloFinanceiroClienteInline(admin.TabularInline):
    model = TituloFinanceiro
    fk_name = 'pessoa'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'numero_documento',
        'parcela_numero',
        'parcela_total',
        'origem',
        'data_vencimento',
        'valor_original',
        'valor_pago',
        'saldo_devedor',
        'status',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Título a Receber'
    verbose_name_plural = 'Contas a Receber / Títulos Financeiros (Últimos 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(tipo='RECEBER').order_by('-data_vencimento', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(TituloFinanceiro.objects.filter(pessoa_id=object_id, tipo='RECEBER').order_by('-data_vencimento', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


@admin.register(Pessoas)
class PessoasAdmin(BaseAdmin):
    list_display = (
        'id', 'razao_nome', 'fantasia_contato', 'tipo_pessoa',
        'funcionario', 'juridica_fisica', 'cnpj_cpf', 'celular', 'email'
    )
    list_filter = ('tipo_pessoa', 'funcionario', 'juridica_fisica', 'codigo_cidade__uf')
    search_fields = ('razao_nome', 'fantasia_contato', 'cnpj_cpf', 'inscricao_rg', 'email', 'celular')
    autocomplete_fields = ('codigo_cidade',)
    inlines = [
        EquipamentoClienteInline,
        VendaClienteInline,
        OrdemServicoClienteInline,
        TituloFinanceiroClienteInline,
    ]
    readonly_fields = BaseAdmin.readonly_fields + (
        'resumo_total_vendas',
        'resumo_total_os',
        'resumo_saldo_devedor',
        'resumo_os_em_aberto',
    )

    class Media:
        js = ('cadastro/js/masks.js',)

    fieldsets = (
        ('Identificação Principal', {
            'fields': (
                ('tipo_pessoa', 'funcionario', 'juridica_fisica'),
                'razao_nome',
                'fantasia_contato',
                ('cnpj_cpf', 'inscricao_rg'),
                'dt_nasc_fund',
            )
        }),
        ('Informações de Contato', {
            'fields': (
                ('email', 'celular'),
                ('telefone', 'telefone2'),
            )
        }),
        ('Endereço e Localização', {
            'fields': (
                ('cep', 'codigo_cidade'),
                ('endereco', 'numero'),
                ('bairro', 'complemento'),
                'caixa_postal',
            )
        }),
        ('Resumo Comercial e Financeiro', {
            'classes': ('collapse',),
            'fields': (
                ('resumo_total_vendas', 'resumo_total_os'),
                ('resumo_saldo_devedor', 'resumo_os_em_aberto'),
                ('primeira_compra', 'ultima_compra'),
            )
        }),
        ('Mídia e Observações', {
            'classes': ('collapse',),
            'fields': (
                'foto',
                'obs',
            )
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Total em Compras (Vendas)')
    def resumo_total_vendas(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        total = obj.vendas.aggregate(total=Sum('valor_total'))['total'] or Decimal('0.00')
        return f"R$ {total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    @admin.display(description='Total em Serviços (OS)')
    def resumo_total_os(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        total = obj.ordens_servico_cliente.aggregate(total=Sum('valor_total'))['total'] or Decimal('0.00')
        return f"R$ {total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    @admin.display(description='Saldo Devedor / A Receber')
    def resumo_saldo_devedor(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        saldo = obj.titulos_financeiros.filter(
            tipo='RECEBER',
            status__in=['ABERTO', 'PARCIAL']
        ).aggregate(total=Sum('saldo_devedor'))['total'] or Decimal('0.00')
        if saldo > 0:
            return f"⚠️ R$ {saldo:,.2f} EM ABERTO".replace(',', 'X').replace('.', ',').replace('X', '.')
        return '✅ R$ 0,00 (Em dia)'

    @admin.display(description='OSs em Aberto')
    def resumo_os_em_aberto(self, obj):
        if not obj or not obj.pk:
            return '0'
        qtd = obj.ordens_servico_cliente.filter(finalizada=False).count()
        return f"{qtd} ordem(ns) em andamento" if qtd > 0 else "Nenhuma OS pendente"

