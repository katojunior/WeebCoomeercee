from django.core.exceptions import ValidationError
from django.db import models, transaction

from cadastro.models import Base


TIPO_MOVIMENTACAO_CHOICES = (
    ('ENTRADA', 'Entrada'),
    ('SAIDA', 'Saída'),
    ('AJUSTE_ENTRADA', 'Ajuste de Inventário (+)'),
    ('AJUSTE_SAIDA', 'Ajuste de Inventário (-)'),
    ('TRANSFERENCIA', 'Transferência entre Localizações'),
)


class EstoqueLocalizacao(Base):
    """Saldo atual de um produto em uma localização física específica."""

    produto = models.ForeignKey(
        'cadastro_produto.Produtos',
        verbose_name='Produto',
        on_delete=models.RESTRICT,
        related_name='saldos_localizacao',
    )
    localizacao = models.ForeignKey(
        'cadastro_produto.LocalizacaoEstoque',
        verbose_name='Localização / Prateleira',
        on_delete=models.RESTRICT,
        related_name='saldos_produto',
    )
    quantidade = models.IntegerField('Quantidade em Estoque', default=0)

    class Meta:
        verbose_name = 'Saldo por Localização'
        verbose_name_plural = 'Saldos por Localização'
        ordering = ['produto__nome', 'localizacao__codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['produto', 'localizacao'],
                name='unique_produto_localizacao',
            ),
        ]

    def __str__(self):
        return f'{self.produto} @ {self.localizacao.codigo}: {self.quantidade}'


class MovimentacaoEstoque(Base):
    """Registro histórico imutável de entradas, saídas, ajustes e transferências."""

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
    quantidade = models.PositiveIntegerField('Quantidade')
    localizacao_origem = models.ForeignKey(
        'cadastro_produto.LocalizacaoEstoque',
        verbose_name='Localização de Origem',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='movimentacoes_origem',
    )
    localizacao_destino = models.ForeignKey(
        'cadastro_produto.LocalizacaoEstoque',
        verbose_name='Localização de Destino',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='movimentacoes_destino',
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
    saldo_anterior_produto = models.IntegerField('Saldo Anterior (Produto)', editable=False, default=0)
    saldo_posterior_produto = models.IntegerField('Saldo Posterior (Produto)', editable=False, default=0)
    saldo_anterior_origem = models.IntegerField('Saldo Anterior (Origem)', editable=False, null=True, blank=True)
    saldo_posterior_origem = models.IntegerField('Saldo Posterior (Origem)', editable=False, null=True, blank=True)
    saldo_anterior_destino = models.IntegerField('Saldo Anterior (Destino)', editable=False, null=True, blank=True)
    saldo_posterior_destino = models.IntegerField('Saldo Posterior (Destino)', editable=False, null=True, blank=True)

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
