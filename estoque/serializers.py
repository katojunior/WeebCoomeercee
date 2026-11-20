from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from cadastro.serializers import BlankToNoneMixin
from cadastro_produto.models import NumeroSerie
from .models import MovimentacaoEstoque
from .services import registrar_movimentacao, validar_movimentacao


class MovimentacaoEstoqueSerializer(BlankToNoneMixin, serializers.ModelSerializer):
    """Serializer auditável para criação e consulta de movimentações do estoque único."""

    blank_to_none_fields = ('pessoa', 'venda', 'ordem_servico')

    produto_nome = serializers.ReadOnlyField(source='produto.nome')
    produto_codigo = serializers.ReadOnlyField(source='produto.codigo_interno')
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    origem_display = serializers.CharField(source='get_origem_display', read_only=True)
    pessoa_nome = serializers.ReadOnlyField(source='pessoa.razao_nome')
    numeros_serie = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=NumeroSerie.objects.all(),
        required=False,
    )
    numeros_serie_codigos = serializers.SerializerMethodField(read_only=True)
    numeros_serie_novos = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        write_only=True,
        required=False,
        default=list,
    )

    class Meta:
        model = MovimentacaoEstoque
        read_only_fields = (
            'saldo_anterior_produto',
            'saldo_posterior_produto',
            'usuario',
            'data_hora',
            'data_hora_atualizada',
        )
        fields = (
            'id',
            'produto',
            'produto_nome',
            'produto_codigo',
            'tipo',
            'tipo_display',
            'origem',
            'origem_display',
            'quantidade',
            'venda',
            'ordem_servico',
            'numeros_serie',
            'numeros_serie_codigos',
            'numeros_serie_novos',
            'pessoa',
            'pessoa_nome',
            'documento_referencia',
            'motivo',
            'observacoes',
            'saldo_anterior_produto',
            'saldo_posterior_produto',
            'usuario',
            'data_hora',
            'data_hora_atualizada',
        )

    def get_numeros_serie_codigos(self, obj):
        return list(obj.numeros_serie.values_list('numero_serie', flat=True))

    def validate(self, attrs):
        seriais = attrs.get('numeros_serie', [])
        novos_seriais = attrs.get('numeros_serie_novos', [])
        mov_preview = MovimentacaoEstoque(
            produto=attrs.get('produto'),
            tipo=attrs.get('tipo'),
            origem=attrs.get('origem') or 'MANUAL',
            quantidade=attrs.get('quantidade'),
            venda=attrs.get('venda'),
            ordem_servico=attrs.get('ordem_servico'),
            pessoa=attrs.get('pessoa'),
            documento_referencia=attrs.get('documento_referencia'),
            motivo=attrs.get('motivo'),
            observacoes=attrs.get('observacoes'),
        )
        try:
            validar_movimentacao(
                mov_preview,
                seriais=seriais,
                novos_seriais=novos_seriais,
                verificar_saldo=True,
                permitir_saldo_negativo=False,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
            raise serializers.ValidationError(detail)
        return attrs

    def create(self, validated_data):
        seriais = validated_data.pop('numeros_serie', [])
        novos_seriais = validated_data.pop('numeros_serie_novos', [])
        request = self.context.get('request')
        usuario = request.user.username if request and request.user.is_authenticated else None
        try:
            return registrar_movimentacao(
                numeros_serie=seriais,
                numeros_serie_novos=novos_seriais,
                usuario=usuario,
                **validated_data,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
            raise serializers.ValidationError(detail)
