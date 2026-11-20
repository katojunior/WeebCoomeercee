from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction

from cadastro.models import Base


TIPO_MOVIMENTACAO_CHOICES = (
    ('ENTRADA', 'Entrada'),
    ('SAIDA', 'Saída'),
    ('AJUSTE_ENTRADA', 'Ajuste de Inventário (+)'),
    ('AJUSTE_SAIDA', 'Ajuste de Inventário (-)'),
)

ORIGEM_MOVIMENTACAO_CHOICES = (
    ('MANUAL', 'Lançamento Manual / Ajuste'),
    ('VENDA', 'Venda'),
    ('ORDEM_SERVICO', 'Ordem de Serviço'),
    ('COMPRA', 'Compra / Entrada NF'),
    ('ESTORNO', 'Estorno / Reabertura'),
)


class MovimentacaoEstoque(Base):
    """Registro histórico imutável de entradas, saídas e ajustes do estoque único."""

    produto = models.ForeignKey(
        'cadastro_produto.Produtos',
        verbose_name='Produto',
        on_delete=models.RESTRICT,
        related_name='movimentacoes_estoque',
    )
    tipo = models.CharField(
        'Tipo de Movimentação',
        max_length=20,
        choices=TIPO_MOVIMENTACAO_CHOICES,
    )
    origem = models.CharField(
        'Origem',
        max_length=20,
        choices=ORIGEM_MOVIMENTACAO_CHOICES,
        default='MANUAL',
        db_index=True,
    )
    quantidade = models.DecimalField(
        'Quantidade',
        max_digits=10,
        decimal_places=3,
    )
    venda = models.ForeignKey(
        'vendas.Venda',
        verbose_name='Venda de Origem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentacoes_estoque',
    )
    ordem_servico = models.ForeignKey(
        'ordem_servico.OrdemServico',
        verbose_name='OS de Origem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentacoes_estoque',
    )
    numeros_serie = models.ManyToManyField(
        'cadastro_produto.NumeroSerie',
        verbose_name='Números de Série',
        blank=True,
        related_name='movimentacoes_estoque',
    )
    pessoa = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Cliente / Fornecedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentacoes_estoque',
    )
    documento_referencia = models.CharField('Documento / NF / Pedido', max_length=60, blank=True, null=True)
    motivo = models.CharField('Motivo / Justificativa', max_length=150, blank=True, null=True)
    observacoes = models.TextField('Observações', blank=True, null=True)

    # Snapshots de auditoria gravados automaticamente no ato da movimentação
    saldo_anterior_produto = models.DecimalField(
        'Saldo Anterior (Produto)',
        max_digits=12,
        decimal_places=3,
        editable=False,
        default=Decimal('0.000'),
    )
    saldo_posterior_produto = models.DecimalField(
        'Saldo Posterior (Produto)',
        max_digits=12,
        decimal_places=3,
        editable=False,
        default=Decimal('0.000'),
    )

    class Meta:
        verbose_name = 'Movimentação de Estoque'
        verbose_name_plural = 'Movimentações de Estoque'
        ordering = ['-data_hora', '-id']

    def clean(self):
        super().clean()
        if getattr(self, '_validado_via_servico', False):
            return
        from .services import validar_movimentacao
        validar_movimentacao(self)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                'Movimentações de estoque são imutáveis e não podem ser alteradas. '
                'Registre um ajuste ou movimentação inversa.'
            )

        if self.documento_referencia:
            self.documento_referencia = self.documento_referencia.strip().upper()
        if self.motivo:
            self.motivo = self.motivo.strip()

        if getattr(self, '_aplicado_via_servico', False):
            super().save(*args, **kwargs)
            return

        from .services import aplicar_movimentacao
        with transaction.atomic():
            aplicar_movimentacao(self)
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            'Movimentações de estoque não podem ser excluídas para preservar o histórico de auditoria.'
        )

    def __str__(self):
        return f'#{self.pk or "NOVO"} {self.get_tipo_display()} - {self.produto.nome} (Qtd: {self.quantidade})'
