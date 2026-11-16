from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from unidecode import unidecode

from cadastro.models import Base


TIPO_TITULO_CHOICES = (
    ('RECEBER', 'Conta a Receber'),
    ('PAGAR', 'Conta a Pagar'),
)

STATUS_TITULO_CHOICES = (
    ('ABERTO', 'Em Aberto'),
    ('PARCIAL', 'Baixa Parcial'),
    ('PAGO', 'Quitado'),
    ('CANCELADO', 'Cancelado'),
)

ORIGEM_TITULO_CHOICES = (
    ('VENDA', 'Venda'),
    ('ORDEM_SERVICO', 'Ordem de Serviço'),
    ('COMPRA', 'Compra / Entrada'),
    ('MANUAL', 'Lançamento Manual'),
)

TIPO_CONTA_CHOICES = (
    ('CAIXA_FISICO', 'Caixa Físico / Balcão'),
    ('CONTA_CORRENTE', 'Conta Corrente Bancária'),
    ('POUPANCA', 'Conta Poupança'),
    ('APLICACAO', 'Aplicação Financeira'),
)

FORMA_PAGAMENTO_CHOICES = (
    ('DINHEIRO', 'Dinheiro'),
    ('PIX', 'PIX'),
    ('CARTAO_CREDITO', 'Cartão de Crédito'),
    ('CARTAO_DEBITO', 'Cartão de Débito'),
    ('BOLETO', 'Boleto Bancário'),
    ('TRANSFERENCIA', 'Transferência Bancária (TED/DOC)'),
    ('CHEQUE', 'Cheque'),
    ('PROMISSORIA', 'Nota Promissória'),
    ('OUTROS', 'Outros'),
)

TIPO_CATEGORIA_CHOICES = (
    ('RECEITA', 'Receita'),
    ('DESPESA', 'Despesa'),
)


class ContaBancaria(Base):
    """Conta bancária ou caixa físico para movimentação e conciliação financeira."""

    descricao = models.CharField('Descrição da Conta / Caixa', max_length=100)
    tipo_conta = models.CharField('Tipo de Conta', max_length=20, choices=TIPO_CONTA_CHOICES, default='CONTA_CORRENTE')
    banco_nome = models.CharField('Banco', max_length=100, blank=True, null=True)
    agencia = models.CharField('Agência', max_length=20, blank=True, null=True)
    conta = models.CharField('Número da Conta', max_length=30, blank=True, null=True)
    saldo_inicial = models.DecimalField('Saldo Inicial (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ativo = models.BooleanField('Ativo?', default=True)
    observacoes = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Conta Bancária / Caixa'
        verbose_name_plural = 'Contas Bancárias e Caixas'
        ordering = ['descricao']

    def save(self, *args, **kwargs):
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        if self.banco_nome:
            self.banco_nome = unidecode(self.banco_nome).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        ag = f" (Ag: {self.agencia})" if self.agencia else ""
        return f"{self.descricao}{ag}"


class CategoriaFinanceira(Base):
    """Plano de contas e categorização de receitas e despesas."""

    nome = models.CharField('Nome da Categoria', max_length=100)
    tipo = models.CharField('Tipo', max_length=10, choices=TIPO_CATEGORIA_CHOICES, default='DESPESA')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Categoria Financeira (Plano de Contas)'
        verbose_name_plural = 'Categorias Financeiras'
        ordering = ['tipo', 'nome']

    def save(self, *args, **kwargs):
        if self.nome:
            self.nome = unidecode(self.nome).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.nome}"


class TituloFinanceiro(Base):
    """Título financeiro unificado (Contas a Receber e Contas a Pagar)."""

    tipo = models.CharField('Tipo do Título', max_length=10, choices=TIPO_TITULO_CHOICES, default='RECEBER')
    pessoa = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Cliente / Fornecedor / Favorecido',
        on_delete=models.RESTRICT,
        related_name='titulos_financeiros',
    )
    categoria = models.ForeignKey(
        'financeiro.CategoriaFinanceira',
        verbose_name='Categoria / Plano de Contas',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='titulos',
    )
    origem = models.CharField('Origem', max_length=20, choices=ORIGEM_TITULO_CHOICES, default='MANUAL')
    venda = models.ForeignKey(
        'vendas.Venda',
        verbose_name='Venda de Origem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='titulos_financeiros',
    )
    ordem_servico = models.ForeignKey(
        'ordem_servico.OrdemServico',
        verbose_name='OS de Origem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='titulos_financeiros',
    )
    numero_documento = models.CharField('Nº Documento / NF', max_length=60, blank=True, null=True)
    parcela_numero = models.IntegerField('Nº Parcela', default=1)
    parcela_total = models.IntegerField('Total de Parcelas', default=1)
    descricao = models.CharField('Descrição / Histórico', max_length=200)

    data_emissao = models.DateField('Data de Emissão', default=timezone.now)
    data_vencimento = models.DateField('Data de Vencimento')

    valor_original = models.DecimalField('Valor Original (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField('Valor Pago (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    saldo_devedor = models.DecimalField('Saldo Devedor (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    status = models.CharField('Status', max_length=15, choices=STATUS_TITULO_CHOICES, default='ABERTO')
    forma_pagamento_prevista = models.CharField('Forma de Pagto Prevista', max_length=60, blank=True, null=True)
    observacoes = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Título Financeiro'
        verbose_name_plural = 'Títulos Financeiros'
        ordering = ['data_vencimento', 'id']

    def save(self, *args, **kwargs):
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        # Se for novo registro e não tiver saldo calculado, inicializa com valor_original
        if self._state.adding and (self.saldo_devedor == Decimal('0.00') and self.valor_pago == Decimal('0.00')):
            self.saldo_devedor = self.valor_original
        super().save(*args, **kwargs)

    def atualizar_saldo_e_status(self, salvar=True):
        """Recalcula o saldo e status com base nas baixas efetuadas."""
        agregado = self.baixas.aggregate(
            total_pago=Sum('valor_pago'),
            total_juros=Sum('juros_multa'),
            total_desconto=Sum('desconto'),
        )
        total_pago = agregado['total_pago'] or Decimal('0.00')
        total_juros = agregado['total_juros'] or Decimal('0.00')
        total_desconto = agregado['total_desconto'] or Decimal('0.00')

        self.valor_pago = total_pago

        # Saldo = Valor Original + Juros - Descontos - Total Pago
        saldo_calculado = (self.valor_original + total_juros - total_desconto) - total_pago
        self.saldo_devedor = max(Decimal('0.00'), saldo_calculado)

        if self.status != 'CANCELADO':
            if self.saldo_devedor == Decimal('0.00') and self.valor_pago > Decimal('0.00'):
                self.status = 'PAGO'
            elif self.valor_pago > Decimal('0.00') and self.saldo_devedor > Decimal('0.00'):
                self.status = 'PARCIAL'
            elif self.valor_pago == Decimal('0.00'):
                self.status = 'ABERTO'

        if salvar:
            self.save(update_fields=['valor_pago', 'saldo_devedor', 'status'])
        return self.saldo_devedor

    def __str__(self):
        parcela = f" ({self.parcela_numero}/{self.parcela_total})" if self.parcela_total > 1 else ""
        return f"[{self.get_tipo_display()}] #{self.id:06d}{parcela} - {self.pessoa.razao_nome} - R$ {self.valor_original} ({self.get_status_display()})"


class ContaReceberManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(tipo='RECEBER')


class ContaReceber(TituloFinanceiro):
    """Proxy model para visualização e gestão focada em Contas a Receber."""
    objects = ContaReceberManager()

    class Meta:
        proxy = True
        verbose_name = 'Conta a Receber'
        verbose_name_plural = 'Contas a Receber'

    def save(self, *args, **kwargs):
        self.tipo = 'RECEBER'
        super().save(*args, **kwargs)


class ContaPagarManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(tipo='PAGAR')


class ContaPagar(TituloFinanceiro):
    """Proxy model para visualização e gestão focada em Contas a Pagar."""
    objects = ContaPagarManager()

    class Meta:
        proxy = True
        verbose_name = 'Conta a Pagar'
        verbose_name_plural = 'Contas a Pagar'

    def save(self, *args, **kwargs):
        self.tipo = 'PAGAR'
        super().save(*args, **kwargs)


class BaixaTitulo(Base):
    """Registro de quitação total ou parcial de um título financeiro."""

    titulo = models.ForeignKey(
        'financeiro.TituloFinanceiro',
        verbose_name='Título Financeiro',
        on_delete=models.CASCADE,
        related_name='baixas',
    )
    conta_bancaria = models.ForeignKey(
        'financeiro.ContaBancaria',
        verbose_name='Conta / Caixa de Liquidação',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='baixas',
    )
    data_pagamento = models.DateField('Data do Pagamento / Quitação', default=timezone.now)
    valor_pago = models.DecimalField('Valor Pago (R$)', max_digits=12, decimal_places=2)
    juros_multa = models.DecimalField('Juros / Multa (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    desconto = models.DecimalField('Desconto (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    forma_pagamento = models.CharField(
        'Forma de Pagamento',
        max_length=20,
        choices=FORMA_PAGAMENTO_CHOICES,
        default='DINHEIRO',
    )
    identificador_transacao = models.CharField('ID Transação / PIX / Cheque / Doc', max_length=100, blank=True, null=True)
    observacoes = models.TextField('Observações da Baixa', blank=True, null=True)

    class Meta:
        verbose_name = 'Baixa de Título'
        verbose_name_plural = 'Baixas de Títulos'
        ordering = ['-data_pagamento', '-id']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.titulo.atualizar_saldo_e_status()

    def delete(self, *args, **kwargs):
        titulo = self.titulo
        super().delete(*args, **kwargs)
        titulo.atualizar_saldo_e_status()

    def __str__(self):
        return f"Baixa #{self.id} de R$ {self.valor_pago} em {self.data_pagamento} ({self.get_forma_pagamento_display()})"
