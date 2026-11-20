from django.urls import path

from .views import (
    CategoriaAPIView,
    CategoriasAPIView,
    MarcaAPIView,
    MarcasAPIView,
    NumeroSerieAPIView,
    NumerosSerieAPIView,
    ProdutoAPIView,
    ProdutosAPIView,
    UnidadeMedidaAPIView,
    UnidadesMedidaAPIView,
)


urlpatterns = [
    path('categorias/', CategoriasAPIView.as_view(), name='categorias'),
    path('categorias/<int:pk>/', CategoriaAPIView.as_view(), name='categoria'),

    path('marcas/', MarcasAPIView.as_view(), name='marcas'),
    path('marcas/<int:pk>/', MarcaAPIView.as_view(), name='marca'),

    path('unidades-medida/', UnidadesMedidaAPIView.as_view(), name='unidades_medida'),
    path('unidades-medida/<int:pk>/', UnidadeMedidaAPIView.as_view(), name='unidade_medida'),

    path('produtos/', ProdutosAPIView.as_view(), name='produtos'),
    path('produtos/<int:pk>/', ProdutoAPIView.as_view(), name='produto'),

    path('numeros-serie/', NumerosSerieAPIView.as_view(), name='numeros_serie'),
    path('numeros-serie/<int:pk>/', NumeroSerieAPIView.as_view(), name='numero_serie'),
]

