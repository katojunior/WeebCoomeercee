from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Estado, Cidade, Pessoas, Pessoa, Cliente
from .serializers import EstadoSerializer, CidadeSerializer, PessoasSerializer, PessoaSerializer, ClienteSerializer

class EstadoAPIView(APIView):
    def get(self, request):
        estados = Estado.objects.all()
        serializer = EstadoSerializer(estados, many=True) 
        return Response(serializer.data)
    def post(self, request):
        is_many = isinstance(request.data, list) #se acaso for uma lista de objetos
        serializer = EstadoSerializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CidadeAPIView(APIView):
    def get(self, request):
        cidades = Cidade.objects.all()
        serializer = CidadeSerializer(cidades, many=True)
        return Response(serializer.data)
    def post(self, request):
        is_many = isinstance(request.data, list) #se acaso for uma lista de objetos
        serializer = CidadeSerializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        

class PessoasAPIView(APIView):
    def get(self, request):
        pessoas = Pessoas.objects.all()
        serializer = PessoasSerializer(pessoas, many=True)
        return Response(serializer.data)
    def post(self, request):
        is_many = isinstance(request.data, list) #se acaso for uma lista de objetos        
        serializer = PessoasSerializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# Aliases para compatibilidade
PessoaAPIView = PessoasAPIView
ClienteAPIView = PessoasAPIView
