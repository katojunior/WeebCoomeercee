import re

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from cadastro.admin import AUDITORIA_FIELDSET, BaseAdmin
from .models import EstoqueLocalizacao, MovimentacaoEstoque
from .services import aplicar_movimentacao, normalizar_lista_novos_seriais, validar_movimentacao


def _parse_novos_seriais_texto(texto):
    if not texto:
        return []
    brutos = re.split(r'[\r\n,;]+', texto)
    return normalizar_lista_novos_seriais(brutos)


class MovimentacaoEstoqueForm(forms.ModelForm):
    """Formulário do Admin com suporte a entrada em lote de novos S/N e validação prévia."""

    numeros_serie_novos = forms.CharField(
        label='Novos Números de Série (Entradas)',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Um número de série por linha ou separados por vírgula',
        }),
        help_text=(
            'Para entradas de produtos com controle de S/N, informe aqui os novos seriais '
            'que ainda não estão cadastrados.'
        ),
    )

    class Meta:
        model = MovimentacaoEstoque
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        novos_seriais = _parse_novos_seriais_texto(cleaned_data.get('numeros_serie_novos'))
        cleaned_data['_novos_seriais_lista'] = novos_seriais
        seriais = list(cleaned_data.get('numeros_serie') or [])

        mov_preview = MovimentacaoEstoque(
            produto=cleaned_data.get('produto'),
            tipo=cleaned_data.get('tipo'),
            quantidade=cleaned_data.get('quantidade'),
            localizacao_origem=cleaned_data.get('localizacao_origem'),
            localizacao_destino=cleaned_data.get('localizacao_destino'),
            pessoa=cleaned_data.get('pessoa'),
            documento_referencia=cleaned_data.get('documento_referencia'),
            motivo=cleaned_data.get('motivo'),
            observacoes=cleaned_data.get('observacoes'),
        )
        try:
            validar_movimentacao(
                mov_preview,
                seriais=seriais,
                novos_seriais=novos_seriais,
                verificar_saldo=True,
            )
            self.instance._validado_via_servico = True
        except ValidationError as exc:
            if hasattr(exc, 'message_dict'):
                for campo, mensagens in exc.message_dict.items():
                    destino = campo if campo in self.fields else None
                    for msg in mensagens:
                        self.add_error(destino, msg)
            else:
                raise
        return cleaned_data


@admin.register(EstoqueLocalizacao)
class EstoqueLocalizacaoAdmin(BaseAdmin):
    """Visualização somente leitura dos saldos de estoque por localização."""

    list_display = ('id', 'produto', 'localizacao', 'quantidade', 'data_hora_atualizada')
    list_filter = ('localizacao', 'localizacao__setor', 'produto__marca', 'produto__categoria')
    search_fields = (
        'produto__nome',
        'produto__codigo_interno',
        'localizacao__codigo',
        'localizacao__setor',
    )
    readonly_fields = ('produto', 'localizacao', 'quantidade') + BaseAdmin.readonly_fields
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        ('Saldo por Localização', {
            'fields': (
                'produto',
                'localizacao',
                'quantidade',
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(BaseAdmin):
    """Administração de movimentações imutáveis com trilha de auditoria."""

    form = MovimentacaoEstoqueForm
    list_display = (
        'id', 'data_hora', 'tipo', 'produto', 'quantidade',
        'localizacao_origem', 'localizacao_destino',
        'saldo_anterior_produto', 'saldo_posterior_produto',
        'documento_referencia', 'usuario',
    )
    list_filter = (
        'tipo', 'localizacao_origem', 'localizacao_destino',
        'produto__marca', 'produto__categoria', 'data_hora',
    )
    search_fields = (
        'produto__nome', 'produto__codigo_interno',
        'documento_referencia', 'motivo',
        'numeros_serie__numero_serie', 'pessoa__razao_nome',
    )
    autocomplete_fields = ('produto', 'localizacao_origem', 'localizacao_destino', 'pessoa', 'numeros_serie')
    readonly_fields = (
        'saldo_anterior_produto',
        'saldo_posterior_produto',
        'saldo_anterior_origem',
        'saldo_posterior_origem',
        'saldo_anterior_destino',
        'saldo_posterior_destino',
    ) + BaseAdmin.readonly_fields
    actions = None

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        seriais = list(form.cleaned_data.get('numeros_serie') or [])
        novos_seriais = form.cleaned_data.get('_novos_seriais_lista') or []
        seriais_finais = aplicar_movimentacao(
            obj,
            seriais=seriais,
            novos_seriais=novos_seriais,
        )
        obj._seriais_finais = seriais_finais
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        seriais_finais = getattr(form.instance, '_seriais_finais', None)
        if seriais_finais is not None:
            form.instance.numeros_serie.set(seriais_finais)

    def get_fieldsets(self, request, obj=None):
        seriais_fields = ('numeros_serie',) if obj else ('numeros_serie', 'numeros_serie_novos')
        return (
            ('Dados da Movimentação', {
                'fields': (
                    ('produto', 'tipo', 'quantidade'),
                    ('localizacao_origem', 'localizacao_destino'),
                )
            }),
            ('Rastreamento / Números de Série', {
                'fields': seriais_fields,
            }),
            ('Origem Comercial e Justificativa', {
                'fields': (
                    ('pessoa', 'documento_referencia'),
                    'motivo',
                    'observacoes',
                )
            }),
            ('Auditoria de Saldos', {
                'fields': (
                    ('saldo_anterior_produto', 'saldo_posterior_produto'),
                    ('saldo_anterior_origem', 'saldo_posterior_origem'),
                    ('saldo_anterior_destino', 'saldo_posterior_destino'),
                )
            }),
            AUDITORIA_FIELDSET,
        )
