from django.urls import path

from .views import (
    MovimentacaoEstoqueAPIView,
    MovimentacoesEstoqueAPIView,
)


urlpatterns = [
    path('movimentacoes-estoque/', MovimentacoesEstoqueAPIView.as_view(), name='movimentacoes_estoque'),
    path('movimentacoes-estoque/<int:pk>/', MovimentacaoEstoqueAPIView.as_view(), name='movimentacao_estoque'),
]
