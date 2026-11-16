from django.contrib import admin

from cadastro.admin import AUDITORIA_FIELDSET, BaseAdmin
from .models import (
    Categoria,
    LocalizacaoEstoque,
    Marca,
    NumeroSerie,
    Produtos,
    UnidadeMedida,
)


@admin.register(Categoria)
class CategoriaAdmin(BaseAdmin):
    """Administração de categorias hierárquicas de produtos."""

    list_display = ('id', 'nome', 'categoria_pai', 'ativo')
    list_filter = ('ativo', 'categoria_pai')
    search_fields = ('nome', 'categoria_pai__nome')
    list_editable = ('ativo',)
    autocomplete_fields = ('categoria_pai',)

    fieldsets = (
        ('Identificação da Categoria', {
            'fields': (
                'nome',
                'categoria_pai',
                'descricao',
                'ativo',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(Marca)
class MarcaAdmin(BaseAdmin):
    """Administração de marcas e fabricantes."""

    list_display = ('id', 'nome', 'site', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    list_editable = ('ativo',)

    fieldsets = (
        ('Identificação da Marca', {
            'fields': (
                'nome',
                'site',
                'ativo',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(UnidadeMedida)
class UnidadeMedidaAdmin(BaseAdmin):
    """Administração de unidades de medida padronizadas."""

    list_display = ('id', 'sigla', 'descricao', 'permite_fracionado', 'ativo')
    list_filter = ('ativo', 'permite_fracionado')
    search_fields = ('sigla', 'descricao')
    list_editable = ('permite_fracionado', 'ativo')

    fieldsets = (
        ('Identificação da Unidade', {
            'fields': (
                'sigla',
                'descricao',
                ('permite_fracionado', 'ativo'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(LocalizacaoEstoque)
class LocalizacaoEstoqueAdmin(BaseAdmin):
    """Administração de localizações físicas e prateleiras do estoque."""

    list_display = ('id', 'codigo', 'setor', 'descricao', 'ativo')
    list_filter = ('ativo', 'setor')
    search_fields = ('codigo', 'setor', 'descricao')
    list_editable = ('ativo',)

    fieldsets = (
        ('Identificação da Localização', {
            'fields': (
                ('codigo', 'setor'),
                'descricao',
                'ativo',
            )
        }),
        AUDITORIA_FIELDSET,
    )


class NumeroSerieInline(admin.TabularInline):
    """Inline para gerenciamento rápido de números de série dentro do produto."""

    model = NumeroSerie
    extra = 0
    fields = (
        'numero_serie',
        'status',
        'localizacao_estoque',
        'fornecedor',
        'nota_fiscal_entrada',
        'cliente',
        'data_venda',
        'data_fim_garantia',
    )
    readonly_fields = ('data_fim_garantia',)
    autocomplete_fields = ('localizacao_estoque', 'fornecedor', 'cliente')


@admin.register(Produtos)
class ProdutosAdmin(BaseAdmin):
    """Administração de produtos com estoque, preços, fiscal e seriais."""

    list_display = (
        'id', 'codigo_interno', 'nome', 'marca', 'categoria',
        'unidade_medida', 'preco_venda', 'estoque_atual', 'controla_numero_serie', 'ativo'
    )
    list_filter = (
        'ativo', 'marca', 'categoria', 'condicao',
        'controla_numero_serie', 'unidade_medida', 'localizacao_estoque'
    )
    search_fields = (
        'nome', 'codigo_interno', 'codigo_barras', 'part_number',
        'marca__nome', 'categoria__nome', 'unidade_medida__sigla',
        'localizacao_estoque__codigo', 'ncm__codigo', 'cest__codigo', 'cfop__codigo', 'modelo'
    )
    list_editable = ('preco_venda', 'ativo')
    readonly_fields = ('estoque_atual', 'margem_lucro') + BaseAdmin.readonly_fields
    autocomplete_fields = (
        'marca', 'categoria', 'unidade_medida', 'localizacao_estoque',
        'fornecedor', 'ncm', 'cest', 'cfop'
    )
    inlines = [NumeroSerieInline]

    fieldsets = (
        ('Identificação do Produto', {
            'fields': (
                ('codigo_interno', 'codigo_barras', 'part_number'),
                'nome',
                ('marca', 'modelo', 'categoria'),
                ('unidade_medida', 'condicao'),
                'descricao_detalhada',
            )
        }),
        ('Precificação e Margem', {
            'fields': (
                ('preco_custo', 'preco_venda', 'preco_promocional'),
                'margem_lucro',
            )
        }),
        ('Controle de Estoque', {
            'fields': (
                ('estoque_atual', 'estoque_minimo', 'estoque_maximo'),
                'localizacao_estoque',
            )
        }),
        ('Informática e Varejo', {
            'fields': (
                ('controla_numero_serie', 'garantia_meses'),
                'fornecedor',
            )
        }),
        ('Dados Fiscais (NFe Brasil)', {
            'classes': ('collapse',),
            'fields': (
                ('ncm', 'cest'),
                ('cfop', 'origem'),
            )
        }),
        ('Dimensões e Frete', {
            'classes': ('collapse',),
            'fields': (
                ('peso_bruto', 'peso_liquido'),
                ('altura', 'largura', 'comprimento'),
            )
        }),
        ('Status e Mídia', {
            'fields': (
                'ativo',
                'foto',
                'obs',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(NumeroSerie)
class NumeroSerieAdmin(BaseAdmin):
    """Administração de rastreamento individual de números de série."""

    list_display = (
        'id', 'numero_serie', 'produto', 'status', 'localizacao_estoque',
        'fornecedor', 'cliente', 'data_venda', 'data_fim_garantia', 'garantia_valida'
    )
    list_filter = ('status', 'localizacao_estoque', 'produto__marca', 'produto__categoria', 'data_venda')
    search_fields = (
        'numero_serie', 'produto__nome', 'produto__codigo_interno',
        'localizacao_estoque__codigo', 'cliente__razao_nome',
        'fornecedor__razao_nome', 'nota_fiscal_entrada', 'nota_fiscal_saida'
    )
    readonly_fields = ('data_entrada', 'data_fim_garantia') + BaseAdmin.readonly_fields
    autocomplete_fields = ('produto', 'localizacao_estoque', 'fornecedor', 'cliente')

    @admin.display(boolean=True, description='Em Garantia?')
    def garantia_valida(self, obj):
        return obj.esta_em_garantia

    fieldsets = (
        ('Identificação do Número de Série', {
            'fields': (
                'produto',
                'numero_serie',
                ('status', 'localizacao_estoque'),
            )
        }),
        ('Entrada / Fornecedor', {
            'fields': (
                ('fornecedor', 'nota_fiscal_entrada'),
                'data_entrada',
            )
        }),
        ('Venda / Cliente e Garantia', {
            'fields': (
                ('cliente', 'nota_fiscal_saida'),
                ('data_venda', 'data_fim_garantia'),
            )
        }),
        ('Histórico e Assistência Técnica (RMA)', {
            'classes': ('collapse',),
            'fields': (
                'historico_rma',
            )
        }),
        AUDITORIA_FIELDSET,
    )
