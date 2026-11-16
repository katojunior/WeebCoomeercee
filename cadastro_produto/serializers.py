from rest_framework import serializers

from cadastro.serializers import BlankToNoneMixin
from .models import (
    Categoria,
    LocalizacaoEstoque,
    Marca,
    NumeroSerie,
    Produto,
    Produtos,
    UnidadeMedida,
)


class CategoriaSerializer(serializers.ModelSerializer):
    """Serializer para categorias de produtos com suporte a hierarquia."""

    categoria_pai_nome = serializers.ReadOnlyField(source='categoria_pai.nome')

    class Meta:
        model = Categoria
        fields = (
            'id',
            'nome',
            'categoria_pai',
            'categoria_pai_nome',
            'descricao',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )

    def validate(self, attrs):
        categoria_pai = attrs.get('categoria_pai')
        if self.instance and categoria_pai and categoria_pai.pk == self.instance.pk:
            raise serializers.ValidationError({
                'categoria_pai': 'Uma categoria não pode ser pai dela mesma.'
            })
        return attrs


class MarcaSerializer(serializers.ModelSerializer):
    """Serializer para fabricantes e marcas."""

    class Meta:
        model = Marca
        fields = (
            'id',
            'nome',
            'site',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )


class UnidadeMedidaSerializer(serializers.ModelSerializer):
    """Serializer para unidades de medida padronizadas."""

    class Meta:
        model = UnidadeMedida
        fields = (
            'id',
            'sigla',
            'descricao',
            'permite_fracionado',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )


class LocalizacaoEstoqueSerializer(serializers.ModelSerializer):
    """Serializer para localizações físicas e prateleiras do estoque."""

    class Meta:
        model = LocalizacaoEstoque
        fields = (
            'id',
            'codigo',
            'setor',
            'descricao',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )


class ProdutosSerializer(BlankToNoneMixin, serializers.ModelSerializer):
    """Serializer completo de produtos com nomes/siglas relacionados em leitura."""

    blank_to_none_fields = (
        'codigo_interno', 'unidade_medida', 'ncm', 'cest', 'cfop',
        'marca', 'categoria', 'localizacao_estoque', 'fornecedor',
    )
    margem_lucro_calculada = serializers.SerializerMethodField(read_only=True)
    fornecedor_nome = serializers.ReadOnlyField(source='fornecedor.razao_nome')
    marca_nome = serializers.ReadOnlyField(source='marca.nome')
    categoria_nome = serializers.SerializerMethodField(read_only=True)
    unidade_medida_sigla = serializers.ReadOnlyField(source='unidade_medida.sigla')
    localizacao_estoque_codigo = serializers.ReadOnlyField(source='localizacao_estoque.codigo')
    ncm_codigo = serializers.ReadOnlyField(source='ncm.codigo')
    cest_codigo = serializers.ReadOnlyField(source='cest.codigo')
    cfop_codigo = serializers.ReadOnlyField(source='cfop.codigo')

    class Meta:
        model = Produtos
        read_only_fields = ('estoque_atual', 'data_hora', 'data_hora_atualizada')
        fields = (
            'id',
            'codigo_interno',
            'codigo_barras',
            'nome',
            'descricao_detalhada',
            'marca',
            'marca_nome',
            'modelo',
            'part_number',
            'categoria',
            'categoria_nome',
            'unidade_medida',
            'unidade_medida_sigla',
            'condicao',
            'preco_custo',
            'preco_venda',
            'preco_promocional',
            'margem_lucro',
            'margem_lucro_calculada',
            'estoque_atual',
            'estoque_minimo',
            'estoque_maximo',
            'localizacao_estoque',
            'localizacao_estoque_codigo',
            'controla_numero_serie',
            'garantia_meses',
            'fornecedor',
            'fornecedor_nome',
            'ncm',
            'ncm_codigo',
            'cest',
            'cest_codigo',
            'cfop',
            'cfop_codigo',
            'origem',
            'peso_bruto',
            'peso_liquido',
            'altura',
            'largura',
            'comprimento',
            'ativo',
            'foto',
            'obs',
            'data_hora',
            'data_hora_atualizada',
        )

    def get_margem_lucro_calculada(self, obj):
        if obj.preco_custo and obj.preco_venda and obj.preco_custo > 0:
            return round(((obj.preco_venda - obj.preco_custo) / obj.preco_custo) * 100, 2)
        return None

    def get_categoria_nome(self, obj):
        return str(obj.categoria) if obj.categoria else None


# Aliases para compatibilidade
ProdutoSerializer = ProdutosSerializer


class NumeroSerieSerializer(serializers.ModelSerializer):
    """Serializer para números de série vinculados a produtos e pessoas."""

    produto_nome = serializers.ReadOnlyField(source='produto.nome')
    produto_codigo = serializers.ReadOnlyField(source='produto.codigo_interno')
    fornecedor_nome = serializers.ReadOnlyField(source='fornecedor.razao_nome')
    cliente_nome = serializers.ReadOnlyField(source='cliente.razao_nome')
    esta_em_garantia = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    localizacao_estoque_codigo = serializers.ReadOnlyField(source='localizacao_estoque.codigo')

    class Meta:
        model = NumeroSerie
        fields = (
            'id',
            'produto',
            'produto_nome',
            'produto_codigo',
            'numero_serie',
            'status',
            'status_display',
            'localizacao_estoque',
            'localizacao_estoque_codigo',
            'fornecedor',
            'fornecedor_nome',
            'nota_fiscal_entrada',
            'data_entrada',
            'cliente',
            'cliente_nome',
            'nota_fiscal_saida',
            'data_venda',
            'data_fim_garantia',
            'esta_em_garantia',
            'historico_rma',
            'data_hora',
            'data_hora_atualizada',
        )

