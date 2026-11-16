from django.urls import path

from .views import (
    MovimentacaoEstoqueAPIView,
    MovimentacoesEstoqueAPIView,
    SaldoEstoqueAPIView,
    SaldosEstoqueAPIView,
)


urlpatterns = [
    path('saldos-estoque/', SaldosEstoqueAPIView.as_view(), name='saldos_estoque'),
    path('saldos-estoque/<int:pk>/', SaldoEstoqueAPIView.as_view(), name='saldo_estoque'),

    path('movimentacoes-estoque/', MovimentacoesEstoqueAPIView.as_view(), name='movimentacoes_estoque'),
    path('movimentacoes-estoque/<int:pk>/', MovimentacaoEstoqueAPIView.as_view(), name='movimentacao_estoque'),
]

