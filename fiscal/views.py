from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics

from cadastro.views import BatchListCreateAPIView
from .models import Cest, Cfop, Ncm
from .serializers import CestSerializer, CfopSerializer, NcmSerializer


class NcmsAPIView(BatchListCreateAPIView):
    """Lista e cria códigos NCM."""

    queryset = Ncm.objects.all()
    serializer_class = NcmSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo']
    search_fields = ['codigo', 'descricao']
    ordering_fields = ['codigo', 'descricao']
    ordering = ['codigo']


class NcmAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove um código NCM específico."""

    queryset = Ncm.objects.all()
    serializer_class = NcmSerializer


class CestsAPIView(BatchListCreateAPIView):
    """Lista e cria códigos CEST."""

    queryset = Cest.objects.all()
    serializer_class = CestSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo']
    search_fields = ['codigo', 'descricao']
    ordering_fields = ['codigo', 'descricao']
    ordering = ['codigo']


class CestAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove um código CEST específico."""

    queryset = Cest.objects.all()
    serializer_class = CestSerializer


class CfopsAPIView(BatchListCreateAPIView):
    """Lista e cria códigos CFOP."""

    queryset = Cfop.objects.all()
    serializer_class = CfopSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativo', 'tipo_operacao', 'movimenta_estoque']
    search_fields = ['codigo', 'descricao']
    ordering_fields = ['codigo', 'descricao', 'tipo_operacao']
    ordering = ['codigo']


class CfopAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Consulta, atualiza ou remove um código CFOP específico."""

    queryset = Cfop.objects.all()
    serializer_class = CfopSerializer
