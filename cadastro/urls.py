from django.urls import path
from .views import (
    EstadosAPIView, EstadoAPIView,
    CidadesAPIView, CidadeAPIView,
    PessoasAPIView, PessoaAPIView,
    ClientesAPIView, ClienteAPIView,
    EmpresasAPIView, EmpresaAPIView, EmpresaPrincipalAPIView,
)

urlpatterns = [
    path('estados/', EstadosAPIView.as_view(), name='estados'),
    path('estados/<int:pk>/', EstadoAPIView.as_view(), name='estado'),

    path('estados/<int:estado_pk>/cidades/', CidadesAPIView.as_view(), name='estado_cidades'),
    path('estados/<int:estado_pk>/cidades/<int:cidade_pk>/', CidadeAPIView.as_view(), name='estado_cidade'),

    path('cidades/', CidadesAPIView.as_view(), name='cidades'),
    path('cidades/<int:cidade_pk>/', CidadeAPIView.as_view(), name='cidade'),

    path('pessoas/', PessoasAPIView.as_view(), name='pessoas'),
    path('pessoas/<int:pk>/', PessoaAPIView.as_view(), name='pessoa'),

    path('empresas/', EmpresasAPIView.as_view(), name='empresas'),
    path('empresas/principal/', EmpresaPrincipalAPIView.as_view(), name='empresa_principal'),
    path('empresas/<int:pk>/', EmpresaAPIView.as_view(), name='empresa'),

    # Rotas legadas para compatibilidade
    path('clientes/', ClientesAPIView.as_view(), name='clientes'),
    path('clientes/<int:pk>/', ClienteAPIView.as_view(), name='cliente'),
]
