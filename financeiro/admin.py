from django.contrib import admin
from .models import ContaBancaria, CategoriaFinanceira, TituloFinanceiro, ContaReceber, ContaPagar, BaixaTitulo


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
    """Classe base do Admin para auditoria automática."""
    readonly_fields = ('usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada')

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.usuario and request.user.is_authenticated:
                obj.usuario = request.user.username
        else:
            if request.user.is_authenticated:
                obj.usuario_atualizou = request.user.username
        super().save_model(request, obj, form, change)


class BaixaTituloInline(admin.TabularInline):
    model = BaixaTitulo
    extra = 0
    autocomplete_fields = ('conta_bancaria',)
    fields = (
        'data_pagamento', 'valor_pago', 'juros_multa', 'desconto',
        'forma_pagamento', 'conta_bancaria', 'identificador_transacao'
    )


@admin.register(ContaBancaria)
class ContaBancariaAdmin(BaseAdmin):
    list_display = ('id', 'descricao', 'tipo_conta', 'banco_nome', 'agencia', 'conta', 'saldo_inicial', 'ativo')
    list_filter = ('tipo_conta', 'ativo')
    search_fields = ('descricao', 'banco_nome', 'agencia', 'conta')
    fieldsets = (
        ('Identificação da Conta / Caixa', {
            'fields': (
                ('descricao', 'tipo_conta', 'ativo'),
                ('banco_nome', 'agencia', 'conta'),
                ('saldo_inicial',),
            )
        }),
        ('Observações', {
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(BaseAdmin):
    list_display = ('id', 'nome', 'tipo', 'ativo')
    list_filter = ('tipo', 'ativo')
    search_fields = ('nome',)
    fieldsets = (
        ('Categoria do Plano de Contas', {
            'fields': (
                ('nome', 'tipo', 'ativo'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(TituloFinanceiro)
class TituloFinanceiroAdmin(BaseAdmin):
    list_display = (
        'id', 'tipo', 'pessoa', 'origem', 'parcela_display', 'data_vencimento',
        'valor_original', 'valor_pago', 'saldo_devedor', 'status'
    )
    list_filter = ('tipo', 'status', 'origem', 'data_vencimento', 'data_emissao', 'categoria')
    search_fields = (
        'id', 'pessoa__razao_nome', 'pessoa__cnpj_cpf',
        'numero_documento', 'descricao'
    )
    autocomplete_fields = ('pessoa', 'categoria', 'venda', 'ordem_servico')
    inlines = [BaixaTituloInline]

    @admin.display(description='Parcela')
    def parcela_display(self, obj):
        return f"{obj.parcela_numero}/{obj.parcela_total}"


@admin.register(ContaReceber)
class ContaReceberAdmin(BaseAdmin):
    list_display = (
        'id', 'pessoa', 'origem', 'parcela_display', 'data_vencimento',
        'valor_original', 'valor_pago', 'saldo_devedor', 'status'
    )
    list_filter = ('status', 'origem', 'data_vencimento', 'data_emissao', 'categoria')
    search_fields = (
        'id', 'pessoa__razao_nome', 'pessoa__cnpj_cpf',
        'numero_documento', 'descricao'
    )
    autocomplete_fields = ('pessoa', 'categoria', 'venda', 'ordem_servico')
    inlines = [BaixaTituloInline]

    fieldsets = (
        ('Identificação da Conta a Receber', {
            'fields': (
                ('pessoa', 'categoria'),
                ('origem', 'numero_documento'),
                ('venda', 'ordem_servico'),
                'descricao',
            )
        }),
        ('Vencimento e Parcelas', {
            'fields': (
                ('data_emissao', 'data_vencimento'),
                ('parcela_numero', 'parcela_total'),
                'forma_pagamento_prevista',
            )
        }),
        ('Valores e Situação', {
            'fields': (
                ('valor_original', 'valor_pago', 'saldo_devedor'),
                'status',
            )
        }),
        ('Observações', {
            'classes': ('collapse',),
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Parcela')
    def parcela_display(self, obj):
        return f"{obj.parcela_numero}/{obj.parcela_total}"


@admin.register(ContaPagar)
class ContaPagarAdmin(BaseAdmin):
    list_display = (
        'id', 'pessoa', 'origem', 'parcela_display', 'data_vencimento',
        'valor_original', 'valor_pago', 'saldo_devedor', 'status'
    )
    list_filter = ('status', 'origem', 'data_vencimento', 'data_emissao', 'categoria')
    search_fields = (
        'id', 'pessoa__razao_nome', 'pessoa__cnpj_cpf',
        'numero_documento', 'descricao'
    )
    autocomplete_fields = ('pessoa', 'categoria')
    inlines = [BaixaTituloInline]

    fieldsets = (
        ('Identificação da Conta a Pagar', {
            'fields': (
                ('pessoa', 'categoria'),
                ('origem', 'numero_documento'),
                'descricao',
            )
        }),
        ('Vencimento e Parcelas', {
            'fields': (
                ('data_emissao', 'data_vencimento'),
                ('parcela_numero', 'parcela_total'),
                'forma_pagamento_prevista',
            )
        }),
        ('Valores e Situação', {
            'fields': (
                ('valor_original', 'valor_pago', 'saldo_devedor'),
                'status',
            )
        }),
        ('Observações', {
            'classes': ('collapse',),
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Parcela')
    def parcela_display(self, obj):
        return f"{obj.parcela_numero}/{obj.parcela_total}"


@admin.register(BaixaTitulo)
class BaixaTituloAdmin(BaseAdmin):
    list_display = (
        'id', 'titulo', 'data_pagamento', 'valor_pago',
        'juros_multa', 'desconto', 'forma_pagamento', 'conta_bancaria'
    )
    list_filter = ('forma_pagamento', 'data_pagamento', 'conta_bancaria')
    search_fields = (
        'titulo__id', 'titulo__pessoa__razao_nome',
        'identificador_transacao', 'observacoes'
    )
    autocomplete_fields = ('titulo', 'conta_bancaria')
