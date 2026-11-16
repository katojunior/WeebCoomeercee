from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics

from cadastro.views import BatchListCreateAPIView
from .models import (
    Categoria,
    LocalizacaoEstoque,
    Marca,
    NumeroSerie,
    Produtos,
    UnidadeMedida,
)
from .serializers import (
    CategoriaSerializer,
    LocalizacaoEstoqueSerializer,
    MarcaSerializer,
    NumeroSerieSerializer,
    ProdutosSerializer,
    UnidadeMedidaSerializer,
)


class CategoriasAPIView(BatchListCreateAPIView):
    """Lista e cria categorias de produtos."""

    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo', 'categoria_pai']
    search_fields = ['nome', 'descricao']
    ordering_fields = ['nome', 'data_hora']
    ordering = ['nome']


class CategoriaAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove uma categoria específica."""

    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer


class MarcasAPIView(BatchListCreateAPIView):
    """Lista e cria marcas/fabricantes."""

    queryset = Marca.objects.all()
    serializer_class = MarcaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo']
    search_fields = ['nome']
    ordering_fields = ['nome', 'data_hora']
    ordering = ['nome']


class MarcaAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove uma marca específica."""

    queryset = Marca.objects.all()
    serializer_class = MarcaSerializer


class UnidadesMedidaAPIView(BatchListCreateAPIView):
    """Lista e cria unidades de medida."""

    queryset = UnidadeMedida.objects.all()
    serializer_class = UnidadeMedidaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo', 'permite_fracionado']
    search_fields = ['sigla', 'descricao']
    ordering_fields = ['sigla', 'descricao', 'data_hora']
    ordering = ['sigla']


class UnidadeMedidaAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove uma unidade de medida específica."""

    queryset = UnidadeMedida.objects.all()
    serializer_class = UnidadeMedidaSerializer


class LocalizacoesEstoqueAPIView(BatchListCreateAPIView):
    """Lista e cria localizações físicas de estoque."""

    queryset = LocalizacaoEstoque.objects.all()
    serializer_class = LocalizacaoEstoqueSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo', 'setor']
    search_fields = ['codigo', 'setor', 'descricao']
    ordering_fields = ['codigo', 'setor', 'data_hora']
    ordering = ['codigo']


class LocalizacaoEstoqueAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove uma localização física específica."""

    queryset = LocalizacaoEstoque.objects.all()
    serializer_class = LocalizacaoEstoqueSerializer


class ProdutosAPIView(BatchListCreateAPIView):
    """Lista e cria produtos com filtros por atributos e relações."""

    queryset = Produtos.objects.all()
    serializer_class = ProdutosSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'marca',
        'categoria',
        'unidade_medida',
        'localizacao_estoque',
        'ncm',
        'cest',
        'cfop',
        'condicao',
        'ativo',
        'controla_numero_serie',
        'fornecedor',
    ]
    search_fields = [
        'nome',
        'codigo_interno',
        'codigo_barras',
        'part_number',
        'marca__nome',
        'categoria__nome',
        'unidade_medida__sigla',
        'localizacao_estoque__codigo',
        'ncm__codigo',
        'cest__codigo',
        'cfop__codigo',
        'modelo',
    ]
    ordering_fields = ['nome', 'preco_venda', 'estoque_atual', 'data_hora']
    ordering = ['nome']


class ProdutoAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove um produto específico."""

    queryset = Produtos.objects.all()
    serializer_class = ProdutosSerializer


class NumerosSerieAPIView(BatchListCreateAPIView):
    """Lista e cria números de série vinculados a produtos."""

    queryset = NumeroSerie.objects.all()
    serializer_class = NumeroSerieSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['produto', 'status', 'localizacao_estoque', 'fornecedor', 'cliente']
    search_fields = [
        'numero_serie',
        'nota_fiscal_entrada',
        'nota_fiscal_saida',
        'produto__nome',
        'produto__codigo_interno',
    ]
    ordering_fields = ['data_entrada', 'data_venda', 'numero_serie']
    ordering = ['-data_entrada']


class NumeroSerieAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove um número de série específico."""

    queryset = NumeroSerie.objects.all()
    serializer_class = NumeroSerieSerializer
