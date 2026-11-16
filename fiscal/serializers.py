from rest_framework import serializers

from .models import Cest, Cfop, Ncm, normalizar_codigo_fiscal


class FiscalCodigoNormalizerMixin:
    """Normaliza o campo `codigo` removendo pontuação antes da validação."""

    def to_internal_value(self, data):
        if isinstance(data, dict) and data.get('codigo') is not None:
            copied = data.dict() if hasattr(data, 'dict') else data.copy()
            copied['codigo'] = normalizar_codigo_fiscal(copied['codigo'])
            data = copied
        return super().to_internal_value(data)


class NcmSerializer(FiscalCodigoNormalizerMixin, serializers.ModelSerializer):
    """Serializer para tabela de códigos NCM."""

    codigo_formatado = serializers.ReadOnlyField()

    class Meta:
        model = Ncm
        fields = (
            'id',
            'codigo',
            'codigo_formatado',
            'descricao',
            'aliquota_ipi',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )


class CestSerializer(FiscalCodigoNormalizerMixin, serializers.ModelSerializer):
    """Serializer para tabela de códigos CEST."""

    codigo_formatado = serializers.ReadOnlyField()

    class Meta:
        model = Cest
        fields = (
            'id',
            'codigo',
            'codigo_formatado',
            'descricao',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )


class CfopSerializer(FiscalCodigoNormalizerMixin, serializers.ModelSerializer):
    """Serializer para tabela de códigos CFOP."""

    tipo_operacao_display = serializers.CharField(source='get_tipo_operacao_display', read_only=True)

    class Meta:
        model = Cfop
        fields = (
            'id',
            'codigo',
            'descricao',
            'tipo_operacao',
            'tipo_operacao_display',
            'movimenta_estoque',
            'ativo',
            'data_hora',
            'data_hora_atualizada',
        )

