from decimal import Decimal
from datetime import timedelta
from django.db import models, transaction
from django.utils import timezone

from cadastro.models import Base
from financeiro.utils import CONDICAO_PAGAMENTO_CHOICES, money, dividir_valor


STATUS_VENDA_CHOICES = (
    ('ORCAMENTO', 'Orçamento'),
    ('ABERTO', 'Em Aberto'),
    ('FINALIZADO', 'Finalizado'),
    ('CANCELADO', 'Cancelado'),
)


class Venda(Base):
    """Registro de Venda de Produtos e Mercadorias."""

    cliente = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Cliente',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='vendas',
    )
    vendedor = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendas_vendedor',
    )
    status = models.CharField(
        'Status da Venda',
        max_length=20,
        choices=STATUS_VENDA_CHOICES,
        default='FINALIZADO',
    )
    finalizada = models.BooleanField('Finalizada / Concluída?', default=False, db_index=True)
    data_finalizacao = models.DateTimeField('Data/Hora de Finalização', null=True, blank=True)
    data_venda = models.DateTimeField('Data e Hora da Venda', default=timezone.now, null=True, blank=True)
    subtotal = models.DecimalField('Subtotal (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    desconto = models.DecimalField('Desconto (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField('Valor Total (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    forma_pagamento = models.CharField('Forma de Pagamento (Histórico)', max_length=150, blank=True, null=True)

    # --- Faturamento e Parcelamento (Padrão WeebFinManage) ---
    condicao_pagamento = models.CharField(
        'Condição de Pagamento',
        max_length=20,
        choices=CONDICAO_PAGAMENTO_CHOICES,
        default='DINHEIRO',
    )
    conta_destino = models.ForeignKey(
        'financeiro.ContaBancaria',
        verbose_name='Conta / Caixa de Recebimento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendas_recebidas',
        help_text='Caixa ou conta bancária onde entrará o valor pago.',
    )
    numero_parcelas = models.PositiveIntegerField(
        'Nº de Parcelas',
        default=1,
        help_text='1 para pagamento à vista, ou > 1 para parcelamento.',
    )
    intervalo_dias = models.PositiveIntegerField(
        'Intervalo entre Parcelas (dias)',
        default=30,
        help_text='Dias entre os vencimentos de cada parcela (Padrão: 30 dias).',
    )
    data_primeiro_vencimento = models.DateField(
        'Vencimento da 1ª Parcela',
        default=timezone.localdate,
        null=True,
        blank=True,
        help_text='Data de vencimento da 1ª parcela (ou data de quitação à vista).',
    )

    numero_nf = models.CharField('Número NF', max_length=50, blank=True, null=True)
    numero_cupom_fiscal = models.CharField('Cupom Fiscal / CF', max_length=50, blank=True, null=True)
    observacoes = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Venda'
        verbose_name_plural = 'Vendas'
        ordering = ['-id']

    def __str__(self):
        nome_cliente = self.cliente.razao_nome if self.cliente else 'Consumidor / Balcão'
        return f"Venda #{self.id:06d} - {nome_cliente} ({self.get_status_display()})"

    def calcular_totais(self):
        """Calcula subtotal e total com base nos itens cadastrados."""
        total_itens = sum(item.valor_total for item in self.itens.all())
        self.subtotal = total_itens
        self.valor_total = max(Decimal('0.00'), total_itens - (self.desconto or Decimal('0.00')))
        return self.valor_total

    # --- Propriedades de Integração Financeira ---
    @property
    def titulos(self):
        """Retorna os títulos (parcelas) gerados a partir desta venda."""
        return self.titulos_financeiros.order_by('data_vencimento', 'id')

    @property
    def total_pago_financeiro(self):
        return money(sum((t.valor_pago for t in self.titulos), Decimal('0.00')))

    @property
    def total_pendente_financeiro(self):
        return money(sum((t.saldo_devedor for t in self.titulos), Decimal('0.00')))

    @property
    def status_financeiro(self):
        tits = list(self.titulos)
        if not tits:
            return 'SEM TITULOS'
        return 'QUITADO' if all(t.status == 'PAGO' for t in tits) else 'EM ABERTO'

    # --- Métodos de Geração e Estorno Financeiro ---
    def gerar_financeiro(self, usuario=None, quitar_se_avista=True):
        """
        Gera os títulos a receber no app financeiro com base nas condições de parcelamento.
        Se for à vista, cria a BaixaTitulo imediata no caixa/conta selecionada.
        Trava a venda como finalizada.
        """
        from financeiro.models import TituloFinanceiro, BaixaTitulo, CategoriaFinanceira, ContaBancaria
        from cadastro.models import Pessoas

        if self.titulos_financeiros.exists():
            return list(self.titulos_financeiros.all())

        total = self.calcular_totais()
        if total <= Decimal('0.00'):
            self.finalizada = True
            self.status = 'FINALIZADO'
            self.data_finalizacao = timezone.now()
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao', 'subtotal', 'valor_total'])
            return []

        categoria, _ = CategoriaFinanceira.objects.get_or_create(
            nome='VENDAS DE MERCADORIAS',
            defaults={'tipo': 'RECEITA'}
        )

        cliente = self.cliente
        if not cliente:
            cliente = Pessoas.objects.filter(id=0).first() or Pessoas.objects.first()

        n = self.numero_parcelas or 1
        intervalo = self.intervalo_dias or 30
        dt_venc = self.data_primeiro_vencimento or timezone.localdate()
        valores = dividir_valor(total, n)

        is_avista = self.condicao_pagamento in ('DINHEIRO', 'PIX', 'CARTAO_DEBITO') and n == 1
        conta = self.conta_destino or ContaBancaria.objects.filter(tipo_conta='CAIXA_FISICO').first() or ContaBancaria.objects.first()

        titulos_gerados = []
        with transaction.atomic():
            for i in range(n):
                venc = dt_venc + timedelta(days=intervalo * i)
                val = valores[i]

                tit = TituloFinanceiro.objects.create(
                    tipo='RECEBER',
                    pessoa=cliente,
                    categoria=categoria,
                    origem='VENDA',
                    venda=self,
                    numero_documento=f"VND-{self.id:06d}",
                    parcela_numero=i + 1,
                    parcela_total=n,
                    descricao=f"Venda #{self.id:06d} - {cliente.razao_nome}",
                    data_emissao=self.data_venda.date() if self.data_venda else timezone.localdate(),
                    data_vencimento=venc,
                    valor_original=val,
                    saldo_devedor=val,
                    status='ABERTO',
                    forma_pagamento_prevista=self.get_condicao_pagamento_display(),
                    usuario=usuario or self.usuario,
                )

                if is_avista and quitar_se_avista and conta:
                    BaixaTitulo.objects.create(
                        titulo=tit,
                        conta_bancaria=conta,
                        data_pagamento=venc,
                        valor_pago=val,
                        forma_pagamento=self.condicao_pagamento,
                        identificador_transacao=f"AUTO-VND-{self.id}",
                        observacoes=f"Quitação automática no fechamento da Venda #{self.id}",
                        usuario=usuario or self.usuario,
                    )
                    tit.refresh_from_db()

                titulos_gerados.append(tit)

            self.finalizada = True
            self.status = 'FINALIZADO'
            self.data_finalizacao = timezone.now()
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao', 'subtotal', 'valor_total'])

        return titulos_gerados

    def estornar_financeiro(self, usuario=None):
        """Estorna as parcelas e baixas geradas por esta venda e a reabre."""
        with transaction.atomic():
            self.titulos_financeiros.all().delete()
            self.finalizada = False
            self.data_finalizacao = None
            self.status = 'ABERTO'
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao'])


class ItemVenda(Base):
    """Itens e produtos vinculados a uma venda."""

    venda = models.ForeignKey(
        'vendas.Venda',
        verbose_name='Venda',
        on_delete=models.CASCADE,
        related_name='itens',
    )
    produto = models.ForeignKey(
        'cadastro_produto.Produtos',
        verbose_name='Produto',
        on_delete=models.RESTRICT,
        related_name='itens_venda',
    )
    sequencia = models.IntegerField('Sequência / Item', default=1)
    quantidade = models.DecimalField('Quantidade', max_digits=10, decimal_places=3, default=Decimal('1.000'))
    valor_unitario = models.DecimalField('Valor Unitário (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    desconto_unitario = models.DecimalField('Desconto Unitário (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField('Valor Total (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Item da Venda'
        verbose_name_plural = 'Itens das Vendas'
        ordering = ['venda', 'sequencia', 'id']

    def save(self, *args, **kwargs):
        qtd = self.quantidade if self.quantidade is not None else Decimal('1.000')
        unit = self.valor_unitario if self.valor_unitario is not None else Decimal('0.00')
        desc = self.desconto_unitario or Decimal('0.00')
        self.valor_total = (qtd * (unit - desc)).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
        if self.venda_id:
            self.venda.calcular_totais()
            self.venda.save(update_fields=['subtotal', 'valor_total'])

    def delete(self, *args, **kwargs):
        venda = self.venda
        super().delete(*args, **kwargs)
        if venda and venda.pk:
            venda.calcular_totais()
            venda.save(update_fields=['subtotal', 'valor_total'])

    def __str__(self):
        nome_prod = self.produto.nome if self.produto else 'Produto'
        return f"Venda #{self.venda_id} - {self.quantidade}x {nome_prod}"
