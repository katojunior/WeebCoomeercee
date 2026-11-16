from decimal import Decimal
from datetime import timedelta
from django.db import models, transaction
from django.utils import timezone
from unidecode import unidecode

from cadastro.models import Base
from financeiro.utils import CONDICAO_PAGAMENTO_CHOICES, money, dividir_valor


STATUS_ORDEM_CHOICES = (
    ('ORCAMENTO', 'Orçamento'),
    ('AGUARDANDO', 'Aguardando Aprovação / Peça'),
    ('EM_ANDAMENTO', 'Em Andamento'),
    ('PRONTO', 'Pronto / Aguardando Retirada'),
    ('FINALIZADO', 'Finalizado / Entregue'),
    ('CANCELADO', 'Cancelado'),
)

TIPO_ITEM_OS_CHOICES = (
    ('PECA', 'Peça / Produto'),
    ('SERVICO', 'Mão de Obra / Serviço'),
)


class EquipamentoCliente(Base):
    """Equipamento pertencente ao cliente (computador, notebook, impressora, etc.)."""

    cliente = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Cliente Proprietário',
        on_delete=models.RESTRICT,
        related_name='equipamentos',
    )
    descricao = models.CharField('Descrição do Equipamento', max_length=150)
    marca = models.ForeignKey(
        'cadastro_produto.Marca',
        verbose_name='Marca',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipamentos_clientes',
    )
    modelo = models.CharField('Modelo', max_length=80, blank=True, null=True)
    numero_serie = models.CharField('Número de Série (S/N)', max_length=100, blank=True, null=True)
    observacoes = models.TextField('Observações', blank=True, null=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Equipamento do Cliente'
        verbose_name_plural = 'Equipamentos dos Clientes'
        ordering = ['cliente__razao_nome', 'descricao']

    def save(self, *args, **kwargs):
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        if self.modelo:
            self.modelo = unidecode(self.modelo).upper().strip()
        if self.numero_serie:
            self.numero_serie = unidecode(self.numero_serie).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        sn = f" (S/N: {self.numero_serie})" if self.numero_serie else ""
        return f"{self.descricao}{sn}"


class OrdemServico(Base):
    """Cabeçalho de Ordem de Serviço (OS) com cliente, técnico, status e valores."""

    cliente = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Cliente',
        on_delete=models.RESTRICT,
        related_name='ordens_servico_cliente',
    )
    equipamento = models.ForeignKey(
        'ordem_servico.EquipamentoCliente',
        verbose_name='Equipamento Principal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordens_servico',
    )
    tecnico = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Técnico Responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordens_servico_tecnico',
    )
    status = models.CharField(
        'Status da OS',
        max_length=20,
        choices=STATUS_ORDEM_CHOICES,
        default='ORCAMENTO',
    )
    finalizada = models.BooleanField('Finalizada / Concluída?', default=False, db_index=True)
    data_finalizacao = models.DateTimeField('Data/Hora de Finalização', null=True, blank=True)
    data_abertura = models.DateTimeField('Data/Hora de Abertura', default=timezone.now)
    previsao_entrega = models.DateField('Previsão de Entrega', null=True, blank=True)
    data_conclusao = models.DateTimeField('Data/Hora de Conclusão', null=True, blank=True)

    defeito_reclamado = models.TextField('Defeito Reclamado / Queixa do Cliente', blank=True, null=True)
    laudo_tecnico = models.TextField('Laudo Técnico / Solução Executada', blank=True, null=True)

    valor_pecas = models.DecimalField('Total Peças (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_servicos = models.DecimalField('Total Serviços (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    desconto = models.DecimalField('Desconto (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField('Valor Total Final (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    forma_pagamento = models.CharField('Forma de Pagamento', max_length=60, blank=True, null=True)
    condicao_pagamento = models.CharField(
        'Condição de Pagamento',
        max_length=20,
        choices=CONDICAO_PAGAMENTO_CHOICES,
        default='DINHEIRO',
        help_text='Condição de pagamento negociada.',
    )
    conta_destino = models.ForeignKey(
        'financeiro.ContaBancaria',
        verbose_name='Conta / Caixa de Recebimento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordens_servico_recebidas',
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
    observacoes = models.TextField('Observações Internas', blank=True, null=True)

    class Meta:
        verbose_name = 'Ordem de Serviço'
        verbose_name_plural = 'Ordens de Serviço'
        ordering = ['-id']

    def save(self, *args, **kwargs):
        if self.defeito_reclamado:
            self.defeito_reclamado = unidecode(self.defeito_reclamado).upper().strip()
        else:
            self.defeito_reclamado = None

        if self.laudo_tecnico:
            self.laudo_tecnico = unidecode(self.laudo_tecnico).upper().strip()
        else:
            self.laudo_tecnico = None

        if self.forma_pagamento:
            self.forma_pagamento = unidecode(self.forma_pagamento).upper().strip()

        super().save(*args, **kwargs)

    def recalcular_totais(self, salvar=True):
        agregado = self.itens.aggregate(
            total_pecas=models.Sum('valor_total', filter=models.Q(tipo_item='PECA')),
            total_servicos=models.Sum('valor_total', filter=models.Q(tipo_item='SERVICO')),
        )
        self.valor_pecas = agregado['total_pecas'] or Decimal('0.00')
        self.valor_servicos = agregado['total_servicos'] or Decimal('0.00')
        desc = self.desconto or Decimal('0.00')
        self.valor_total = max(Decimal('0.00'), (self.valor_pecas + self.valor_servicos) - desc)
        if salvar and self.pk:
            OrdemServico.objects.filter(pk=self.pk).update(
                valor_pecas=self.valor_pecas,
                valor_servicos=self.valor_servicos,
                valor_total=self.valor_total,
            )
        return self.valor_total

    def __str__(self):
        return f"OS #{self.id:06d} - {self.cliente.razao_nome} ({self.get_status_display()})"

    # --- Propriedades de Integração Financeira ---
    @property
    def titulos(self):
        """Retorna os títulos (parcelas) gerados a partir desta OS."""
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
        Trava a OS como finalizada.
        """
        from financeiro.models import TituloFinanceiro, BaixaTitulo, CategoriaFinanceira, ContaBancaria

        if self.titulos_financeiros.exists():
            return list(self.titulos_financeiros.all())

        total = self.recalcular_totais(salvar=True)
        if total <= Decimal('0.00'):
            self.finalizada = True
            self.status = 'FINALIZADO'
            self.data_finalizacao = timezone.now()
            if not self.data_conclusao:
                self.data_conclusao = timezone.now()
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao', 'data_conclusao', 'valor_pecas', 'valor_servicos', 'valor_total'])
            return []

        categoria, _ = CategoriaFinanceira.objects.get_or_create(
            nome='SERVICOS PRESTADOS',
            defaults={'tipo': 'RECEITA'}
        )

        cliente = self.cliente
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
                    origem='ORDEM_SERVICO',
                    ordem_servico=self,
                    numero_documento=f"OS-{self.id:06d}",
                    parcela_numero=i + 1,
                    parcela_total=n,
                    descricao=f"OS #{self.id:06d} - {cliente.razao_nome}",
                    data_emissao=self.data_abertura.date() if self.data_abertura else timezone.localdate(),
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
                        identificador_transacao=f"AUTO-OS-{self.id}",
                        observacoes=f"Quitação automática no fechamento da OS #{self.id}",
                        usuario=usuario or self.usuario,
                    )
                    tit.refresh_from_db()

                titulos_gerados.append(tit)

            self.finalizada = True
            self.status = 'FINALIZADO'
            self.data_finalizacao = timezone.now()
            if not self.data_conclusao:
                self.data_conclusao = timezone.now()
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao', 'data_conclusao', 'valor_pecas', 'valor_servicos', 'valor_total'])

        return titulos_gerados

    def estornar_financeiro(self, usuario=None):
        """Estorna as parcelas e baixas geradas por esta OS e a reabre."""
        with transaction.atomic():
            self.titulos_financeiros.all().delete()
            self.finalizada = False
            self.data_finalizacao = None
            self.status = 'ORCAMENTO'
            self.save(update_fields=['finalizada', 'status', 'data_finalizacao'])


class ItemOrdemServico(Base):
    """Itens, peças e serviços vinculados a uma Ordem de Serviço."""

    ordem = models.ForeignKey(
        'ordem_servico.OrdemServico',
        verbose_name='Ordem de Serviço',
        on_delete=models.CASCADE,
        related_name='itens',
    )
    equipamento = models.ForeignKey(
        'ordem_servico.EquipamentoCliente',
        verbose_name='Equipamento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens_os',
    )
    produto = models.ForeignKey(
        'cadastro_produto.Produtos',
        verbose_name='Produto / Peça / Serviço',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='itens_ordem_servico',
    )
    descricao_personalizada = models.CharField('Descrição Personalizada', max_length=150, blank=True, null=True)
    tipo_item = models.CharField('Tipo do Item', max_length=10, choices=TIPO_ITEM_OS_CHOICES, default='PECA')
    quantidade = models.DecimalField('Quantidade', max_digits=10, decimal_places=3, default=Decimal('1.000'))
    valor_unitario = models.DecimalField('Valor Unitário (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField('Valor Total (R$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Item / Peça / Serviço da OS'
        verbose_name_plural = 'Itens / Peças / Serviços da OS'
        ordering = ['ordem', 'id']

    def save(self, *args, **kwargs):
        qtd = self.quantidade if self.quantidade is not None else Decimal('1.000')
        unit = self.valor_unitario if self.valor_unitario is not None else Decimal('0.00')
        self.valor_total = (qtd * unit).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
        if self.ordem_id:
            self.ordem.recalcular_totais(salvar=True)

    def delete(self, *args, **kwargs):
        ordem = self.ordem
        super().delete(*args, **kwargs)
        if ordem and ordem.pk:
            ordem.recalcular_totais(salvar=True)

    def __str__(self):
        nome_prod = self.produto.nome if self.produto else (self.descricao_personalizada or 'Item')
        return f"OS #{self.ordem_id} - {self.quantidade}x {nome_prod}"
