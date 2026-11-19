from rest_framework import generics, filters, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import Estado, Cidade, Pessoas, Pessoa, Cliente, Empresa
from .serializers import (
    EstadoSerializer, CidadeSerializer,
    PessoasSerializer, PessoaSerializer, ClienteSerializer,
    EmpresaSerializer,
)


class BatchListCreateAPIView(generics.ListCreateAPIView):
    """Permite envio de objeto único ou lista de objetos em requisições POST."""

    def get_serializer(self, *args, **kwargs):
        # Verifica se os dados enviados no POST são uma lista
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)


class EstadosAPIView(BatchListCreateAPIView):
    queryset = Estado.objects.all()
    serializer_class = EstadoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['uf', 'regiao']
    search_fields = ['uf', 'estado', 'codigoUf']
    ordering_fields = ['estado', 'uf', 'codigoUf']
    ordering = ['estado']


class EstadoAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Estado.objects.all()
    serializer_class = EstadoSerializer


class CidadesAPIView(BatchListCreateAPIView):
    queryset = Cidade.objects.all()
    serializer_class = CidadeSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['uf', 'capital', 'ddd']
    search_fields = ['descricaoCidade', 'descricao_completa', 'codigoIbge']
    ordering_fields = ['descricaoCidade', 'codigoIbge']
    ordering = ['descricaoCidade']

    def _prepare_nested_estado(self, item, estado_pk):
        if not isinstance(item, dict):
            return item
        data = item.dict() if hasattr(item, 'dict') else item.copy()
        uf_val = data.get('uf')
        if uf_val in (None, ''):
            data['uf'] = estado_pk
        elif str(uf_val) != str(estado_pk):
            raise serializers.ValidationError({
                'uf': 'A UF informada no corpo diverge do estado informado na URL.'
            })
        return data

    def get_serializer(self, *args, **kwargs):
        estado_pk = self.kwargs.get('estado_pk')
        if estado_pk and 'data' in kwargs:
            data = kwargs['data']
            if isinstance(data, list):
                kwargs['data'] = [self._prepare_nested_estado(item, estado_pk) for item in data]
            elif isinstance(data, dict):
                kwargs['data'] = self._prepare_nested_estado(data, estado_pk)
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        estado_pk = self.kwargs.get('estado_pk')
        if estado_pk:
            return self.queryset.filter(uf_id=estado_pk)
        return super().get_queryset()


class CidadeAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Cidade.objects.all()
    serializer_class = CidadeSerializer
    lookup_url_kwarg = 'cidade_pk'

    def get_queryset(self):
        estado_pk = self.kwargs.get('estado_pk')
        if estado_pk:
            return self.queryset.filter(uf_id=estado_pk)
        return super().get_queryset()


class PessoasAPIView(BatchListCreateAPIView):
    queryset = Pessoas.objects.all()
    serializer_class = PessoasSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tipo_pessoa', 'juridica_fisica', 'codigo_cidade']
    search_fields = ['razao_nome', 'fantasia_contato', 'cnpj_cpf', 'inscricao_rg']
    ordering_fields = ['razao_nome', 'data_hora']
    ordering = ['razao_nome']


class PessoaAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Pessoas.objects.all()
    serializer_class = PessoasSerializer


# Aliases para compatibilidade
ClientesAPIView = PessoasAPIView
ClienteAPIView = PessoaAPIView


class EmpresasAPIView(BatchListCreateAPIView):
    queryset = Empresa.objects.select_related('cidade', 'cidade__uf').all()
    serializer_class = EmpresaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ativa', 'matriz', 'regime_tributario', 'cidade']
    search_fields = ['razao_social', 'nome_fantasia', 'cnpj', 'inscricao_estadual']
    ordering_fields = ['razao_social', 'nome_fantasia', 'id']
    ordering = ['-matriz', 'razao_social']


class EmpresaAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Empresa.objects.select_related('cidade', 'cidade__uf').all()
    serializer_class = EmpresaSerializer


class EmpresaPrincipalAPIView(APIView):
    """Retorna os dados da empresa matriz/principal ativa (incluindo cabeçalho de impressão)."""

    def get(self, request):
        empresa = Empresa.get_principal()
        if not empresa:
            return Response(
                {'detail': 'Nenhuma empresa cadastrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = EmpresaSerializer(empresa, context={'request': request})
        return Response(serializer.data)

