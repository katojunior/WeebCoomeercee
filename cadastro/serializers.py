from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from unidecode import unidecode
from .models import Estado, Cidade, Pessoas, Pessoa, Cliente
from .validators import (
    formatar_cep,
    formatar_cpf_cnpj,
    formatar_telefone,
    validar_consistencia_pessoa,
)


class BlankToNoneMixin:
    """Converte strings vazias em None para campos únicos opcionais."""
    blank_to_none_fields = ()

    def to_internal_value(self, data):
        if isinstance(data, dict):
            copied = data.dict() if hasattr(data, 'dict') else data.copy()
            for field_name in self.blank_to_none_fields:
                if field_name in copied and isinstance(copied[field_name], str) and not copied[field_name].strip():
                    copied[field_name] = None
            data = copied
        return super().to_internal_value(data)


class EstadoSerializer(BlankToNoneMixin, serializers.ModelSerializer):
    blank_to_none_fields = ('regiao',)

    class Meta:
        model = Estado
        fields = (
            'id',
            'codigoUf',
            'uf',
            'estado',
            'latitude',
            'longitude',
            'regiao'
        )
        # Se você quiser que o ID apareça na resposta da API,
        # mas nunca seja enviado pelo usuário, use:
        # read_only_fields = ['id']

    def to_internal_value(self, data):
        if isinstance(data, dict) and data.get('regiao') and isinstance(data['regiao'], str):
            copied = data.dict() if hasattr(data, 'dict') else data.copy()
            copied['regiao'] = unidecode(copied['regiao']).upper().strip()
            data = copied
        return super().to_internal_value(data)


class CidadeSerializer(BlankToNoneMixin, serializers.ModelSerializer):
    blank_to_none_fields = ('codigoIbge',)

    class Meta:
        model = Cidade
        fields = (
            'id',
            'descricaoCidade',
            'descricao_completa',
            'uf',
            'latitude',
            'longitude',
            'capital',
            'ddd',
            'fusoHorario',
            'codigoIbge'
        )


class PessoasSerializer(BlankToNoneMixin, serializers.ModelSerializer):
    blank_to_none_fields = ('cnpj_cpf', 'cep', 'celular', 'telefone', 'telefone2')

    _FIELD_FORMATTERS = {
        'cnpj_cpf': formatar_cpf_cnpj,
        'cep': formatar_cep,
        'celular': formatar_telefone,
        'telefone': formatar_telefone,
        'telefone2': formatar_telefone,
    }

    def to_internal_value(self, data):
        if isinstance(data, dict):
            copied = data.dict() if hasattr(data, 'dict') else data.copy()
            for field_name, formatter in self._FIELD_FORMATTERS.items():
                if field_name in copied and copied[field_name] is not None:
                    copied[field_name] = formatter(copied[field_name])
            data = copied
        return super().to_internal_value(data)

    def validate(self, attrs):
        juridica_fisica = attrs.get(
            'juridica_fisica',
            getattr(self.instance, 'juridica_fisica', None),
        )
        cnpj_cpf = attrs.get(
            'cnpj_cpf',
            getattr(self.instance, 'cnpj_cpf', None),
        )
        try:
            validar_consistencia_pessoa(juridica_fisica, cnpj_cpf)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    class Meta:
        model = Pessoas
        fields = (
            'id',
            'juridica_fisica',
            'tipo_pessoa',
            'inscricao_rg',
            'cnpj_cpf',
            'razao_nome',
            'fantasia_contato',
            'endereco',
            'numero',
            'complemento',
            'bairro',
            'cep',
            'codigo_cidade',
            'caixa_postal',
            'primeira_compra',
            'ultima_compra',
            'celular',
            'telefone',
            'telefone2',
            'dt_nasc_fund',
            'email',
            'obs',
            'foto'
        )


# Aliases para compatibilidade
PessoaSerializer = PessoasSerializer
ClienteSerializer = PessoasSerializer

