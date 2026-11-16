from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics

from .models import EstoqueLocalizacao, MovimentacaoEstoque
from .serializers import EstoqueLocalizacaoSerializer, MovimentacaoEstoqueSerializer


class SaldosEstoqueAPIView(generics.ListAPIView):
    """Lista os saldos atuais de estoque por produto e localização física."""

    queryset = EstoqueLocalizacao.objects.select_related('produto', 'localizacao').all()
    serializer_class = EstoqueLocalizacaoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['produto', 'localizacao', 'localizacao__setor']
    search_fields = [
        'produto__nome',
        'produto__codigo_interno',
        'localizacao__codigo',
        'localizacao__setor',
    ]
    ordering_fields = ['quantidade', 'produto__nome', 'localizacao__codigo', 'data_hora_atualizada']
    ordering = ['produto__nome', 'localizacao__codigo']


class SaldoEstoqueAPIView(generics.RetrieveAPIView):
    """Consulta um saldo específico por localização."""

    queryset = EstoqueLocalizacao.objects.select_related('produto', 'localizacao').all()
    serializer_class = EstoqueLocalizacaoSerializer


class MovimentacoesEstoqueAPIView(generics.ListCreateAPIView):
    """Lista o histórico imutável e registra novas movimentações de estoque."""

    queryset = (
        MovimentacaoEstoque.objects.select_related(
            'produto',
            'localizacao_origem',
            'localizacao_destino',
            'pessoa',
        )
        .prefetch_related('numeros_serie')
        .all()
    )
    serializer_class = MovimentacaoEstoqueSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['produto', 'tipo', 'localizacao_origem', 'localizacao_destino', 'pessoa']
    search_fields = [
        'produto__nome',
        'produto__codigo_interno',
        'documento_referencia',
        'motivo',
        'numeros_serie__numero_serie',
        'pessoa__razao_nome',
    ]
    ordering_fields = ['data_hora', 'quantidade', 'tipo']
    ordering = ['-data_hora', '-id']


class MovimentacaoEstoqueAPIView(generics.RetrieveAPIView):
    """Consulta os detalhes auditáveis de uma movimentação (somente leitura)."""

    queryset = (
        MovimentacaoEstoque.objects.select_related(
            'produto',
            'localizacao_origem',
            'localizacao_destino',
            'pessoa',
        )
        .prefetch_related('numeros_serie')
        .all()
    )
    serializer_class = MovimentacaoEstoqueSerializer
