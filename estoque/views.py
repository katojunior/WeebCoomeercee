from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics

from .models import MovimentacaoEstoque
from .serializers import MovimentacaoEstoqueSerializer


class MovimentacoesEstoqueAPIView(generics.ListCreateAPIView):
    """Lista o histórico imutável e registra novas movimentações de estoque."""

    queryset = (
        MovimentacaoEstoque.objects.select_related(
            'produto',
            'pessoa',
            'venda',
            'ordem_servico',
        )
        .prefetch_related('numeros_serie')
        .all()
    )
    serializer_class = MovimentacaoEstoqueSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['produto', 'tipo', 'origem', 'pessoa', 'venda', 'ordem_servico']
    search_fields = [
        'produto__nome',
        'produto__codigo_interno',
        'documento_referencia',
        'motivo',
        'numeros_serie__numero_serie',
        'pessoa__razao_nome',
    ]
    ordering_fields = ['data_hora', 'quantidade', 'tipo', 'origem']
    ordering = ['-data_hora', '-id']


class MovimentacaoEstoqueAPIView(generics.RetrieveAPIView):
    """Consulta os detalhes auditáveis de uma movimentação (somente leitura)."""

    queryset = (
        MovimentacaoEstoque.objects.select_related(
            'produto',
            'pessoa',
            'venda',
            'ordem_servico',
        )
        .prefetch_related('numeros_serie')
        .all()
    )
    serializer_class = MovimentacaoEstoqueSerializer
