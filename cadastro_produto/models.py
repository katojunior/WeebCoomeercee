import calendar
import datetime

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from stdimage import StdImageField
from unidecode import unidecode

from cadastro.models import Base, get_file_path


ORIGEM_PRODUTO_CHOICES = (
    (0, '0 - Nacional'),
    (1, '1 - Estrangeira (Importação direta)'),
    (2, '2 - Estrangeira (Adquirida no mercado interno)'),
)

CONDICAO_PRODUTO_CHOICES = (
    ('NOVO', 'NOVO'),
    ('USADO', 'USADO / RECONDICIONADO'),
    ('OPEN_BOX', 'OPEN BOX'),
)

STATUS_SERIAL_CHOICES = (
    ('DISPONIVEL', 'Disponível em Estoque'),
    ('RESERVADO', 'Reservado em Pedido'),
    ('VENDIDO', 'Vendido ao Cliente'),
    ('RMA_CLIENTE', 'Em Garantia / Devolvido por Cliente'),
    ('RMA_FORNECEDOR', 'Enviado para Troca no Fornecedor'),
    ('DEFEITO', 'Avariado / Sem Condição de Uso'),
    ('BAIXADO', 'Baixado / Perda / Descarte'),
)


class Categoria(Base):
    """Categoria hierárquica para organização do catálogo de produtos."""

    nome = models.CharField('Nome da Categoria', max_length=80, unique=True)
    categoria_pai = models.ForeignKey(
        'self',
        verbose_name='Categoria Pai',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='subcategorias',
    )
    descricao = models.TextField('Descrição', blank=True, null=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['nome']

    def clean(self):
        if self.categoria_pai_id and self.categoria_pai_id == self.pk:
            raise ValidationError({'categoria_pai': 'Uma categoria não pode ser pai dela mesma.'})

    def save(self, *args, **kwargs):
        if self.nome:
            self.nome = unidecode(self.nome).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.categoria_pai:
            return f'{self.categoria_pai} > {self.nome}'
        return self.nome or ''


class Marca(Base):
    """Fabricante ou marca comercial de produtos."""

    nome = models.CharField('Nome da Marca', max_length=80, unique=True)
    site = models.URLField('Site Oficial', max_length=200, blank=True, null=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'
        ordering = ['nome']

    def save(self, *args, **kwargs):
        if self.nome:
            self.nome = unidecode(self.nome).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome or ''


class UnidadeMedida(Base):
    """Unidade de medida comercial/fiscal padronizada para produtos."""

    sigla = models.CharField('Sigla', max_length=10, unique=True)
    descricao = models.CharField('Descrição', max_length=60)
    permite_fracionado = models.BooleanField('Permite Fracionado?', default=False)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'
        ordering = ['sigla']

    def save(self, *args, **kwargs):
        if self.sigla:
            self.sigla = unidecode(self.sigla).upper().strip()
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.descricao:
            return f'{self.sigla} - {self.descricao}'
        return self.sigla or ''


class LocalizacaoEstoque(Base):
    """Endereço físico ou prateleira para alocação de estoque."""

    codigo = models.CharField('Código / Prateleira', max_length=30, unique=True)
    setor = models.CharField(
        'Setor',
        max_length=50,
        blank=True,
        null=True,
        help_text='Ex: DEPOSITO, VITRINE, RMA',
    )
    descricao = models.CharField('Descrição', max_length=120, blank=True, null=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Localização de Estoque'
        verbose_name_plural = 'Localizações de Estoque'
        ordering = ['codigo']

    def save(self, *args, **kwargs):
        if self.codigo:
            self.codigo = unidecode(self.codigo).upper().strip()
        if self.setor:
            self.setor = unidecode(self.setor).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.setor:
            return f'{self.codigo} ({self.setor})'
        return self.codigo or ''


class Produtos(Base):
    """Cadastro de produtos para varejo e informática com rastreio opcional de S/N."""

    # Identificação
    codigo_interno = models.CharField('Código Interno / SKU', max_length=50, unique=True, null=True, blank=True)
    codigo_barras = models.CharField('Código de Barras / EAN', max_length=14, blank=True, null=True)
    nome = models.CharField('Nome do Produto', max_length=150)
    descricao_detalhada = models.TextField('Descrição Detalhada / Especificações Técnicas', blank=True, null=True)
    marca = models.ForeignKey(
        'cadastro_produto.Marca',
        verbose_name='Marca / Fabricante',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    modelo = models.CharField('Modelo', max_length=60, blank=True, null=True)
    part_number = models.CharField(
        'Part Number (P/N)',
        max_length=60,
        blank=True,
        null=True,
        help_text='Código do fabricante da peça/componente',
    )
    categoria = models.ForeignKey(
        'cadastro_produto.Categoria',
        verbose_name='Categoria',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    unidade_medida = models.ForeignKey(
        'cadastro_produto.UnidadeMedida',
        verbose_name='Unidade de Medida',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    condicao = models.CharField('Condição', max_length=15, choices=CONDICAO_PRODUTO_CHOICES, default='NOVO')

    # Preços e Margem
    preco_custo = models.DecimalField('Preço de Custo (R$)', max_digits=12, decimal_places=2, default=0.00)
    preco_venda = models.DecimalField('Preço de Venda (R$)', max_digits=12, decimal_places=2, default=0.00)
    preco_promocional = models.DecimalField('Preço Promocional (R$)', max_digits=12, decimal_places=2, null=True, blank=True)
    margem_lucro = models.DecimalField('Margem de Lucro (%)', max_digits=10, decimal_places=2, null=True, blank=True)

    # Estoque
    estoque_atual = models.IntegerField('Estoque Atual', default=0)
    estoque_minimo = models.IntegerField('Estoque Mínimo', default=0)
    estoque_maximo = models.IntegerField('Estoque Máximo', null=True, blank=True)
    localizacao_estoque = models.ForeignKey(
        'cadastro_produto.LocalizacaoEstoque',
        verbose_name='Localização / Prateleira',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )

    # Específico de Informática e Varejo
    controla_numero_serie = models.BooleanField(
        'Controla Número de Série?',
        default=False,
        help_text='Ative para rastrear números de série e RMA/garantia',
    )
    garantia_meses = models.PositiveIntegerField('Garantia (Meses)', default=12, blank=True, null=True)
    fornecedor = models.ForeignKey(
        'cadastro.Pessoas',
        verbose_name='Fornecedor Padrão',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'tipo_pessoa__in': [1, 2]},
        related_name='produtos_fornecidos',
    )

    # Fiscal / Tributário (NFe Brasil)
    ncm = models.ForeignKey(
        'fiscal.Ncm',
        verbose_name='NCM',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    cest = models.ForeignKey(
        'fiscal.Cest',
        verbose_name='CEST',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    cfop = models.ForeignKey(
        'fiscal.Cfop',
        verbose_name='CFOP Padrão',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='produtos',
    )
    origem = models.SmallIntegerField('Origem da Mercadoria', choices=ORIGEM_PRODUTO_CHOICES, default=0)

    # Dimensões e Frete (E-commerce / Logística)
    peso_bruto = models.DecimalField('Peso Bruto (kg)', max_digits=8, decimal_places=3, null=True, blank=True)
    peso_liquido = models.DecimalField('Peso Líquido (kg)', max_digits=8, decimal_places=3, null=True, blank=True)
    altura = models.DecimalField('Altura (cm)', max_digits=6, decimal_places=2, null=True, blank=True)
    largura = models.DecimalField('Largura (cm)', max_digits=6, decimal_places=2, null=True, blank=True)
    comprimento = models.DecimalField('Comprimento (cm)', max_digits=6, decimal_places=2, null=True, blank=True)

    # Status e Imagem
    ativo = models.BooleanField('Ativo?', default=True)
    foto = StdImageField(
        'Foto do Produto',
        upload_to=get_file_path,
        null=True,
        blank=True,
        variations={'thumb': {'width': 480, 'height': 480, 'crop': True}},
    )
    obs = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['nome']

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if not update_fields or 'nome' in update_fields:
            if self.nome:
                self.nome = unidecode(self.nome).upper()
        if not update_fields or 'modelo' in update_fields:
            if self.modelo:
                self.modelo = unidecode(self.modelo).upper()
        if not update_fields or 'codigo_interno' in update_fields:
            self.codigo_interno = unidecode(self.codigo_interno).upper().strip() or None if self.codigo_interno else None
        if not update_fields or 'part_number' in update_fields:
            if self.part_number:
                self.part_number = unidecode(self.part_number).upper()

        # Definir unidade padrão ('UN') quando não informada
        if not self.unidade_medida_id and (not update_fields or 'unidade_medida' in update_fields):
            unidade_padrao = UnidadeMedida.objects.filter(sigla='UN').first()
            if unidade_padrao:
                self.unidade_medida = unidade_padrao

        # Calcular margem de lucro automaticamente se não informada
        if (not update_fields) and self.preco_custo and self.preco_venda and self.preco_custo > 0 and not self.margem_lucro:
            self.margem_lucro = round(((self.preco_venda - self.preco_custo) / self.preco_custo) * 100, 2)

        # Quando controla número de série, o estoque é derivado exclusivamente dos seriais DISPONIVEL
        if self.controla_numero_serie and (not update_fields or 'estoque_atual' not in update_fields):
            if self.pk:
                self.estoque_atual = self.numeros_serie.filter(status='DISPONIVEL').count()
            else:
                self.estoque_atual = 0

        super().save(*args, **kwargs)

    def __str__(self):
        if self.codigo_interno:
            return f'{self.codigo_interno} - {self.nome}'
        return self.nome or ''


# Aliases para compatibilidade
Produto = Produtos


class NumeroSerie(Base):
    """Rastreamento individual de números de série para garantia, venda e RMA."""

    produto = models.ForeignKey(
        'cadastro_produto.Produtos',
        on_delete=models.CASCADE,
        related_name='numeros_serie',
        verbose_name='Produto',
    )
    numero_serie = models.CharField(
        'Número de Série (S/N)',
        max_length=100,
        unique=True,
        help_text='Identificador único do fabricante na etiqueta da peça',
    )
    status = models.CharField(
        'Status do Serial',
        max_length=20,
        choices=STATUS_SERIAL_CHOICES,
        default='DISPONIVEL',
    )
    localizacao_estoque = models.ForeignKey(
        'cadastro_produto.LocalizacaoEstoque',
        verbose_name='Localização Atual',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='numeros_serie',
    )

    # Rastreio de Entrada (Compra / Fornecedor)
    fornecedor = models.ForeignKey(
        'cadastro.Pessoas',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'tipo_pessoa__in': [1, 2]},
        related_name='seriais_fornecidos',
        verbose_name='Fornecedor de Origem',
    )
    nota_fiscal_entrada = models.CharField('NF de Entrada', max_length=50, blank=True, null=True)
    data_entrada = models.DateTimeField('Data de Entrada', auto_now_add=True, null=True, blank=True)

    # Rastreio de Saída (Venda / Cliente)
    cliente = models.ForeignKey(
        'cadastro.Pessoas',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'tipo_pessoa__in': [0, 2]},
        related_name='produtos_comprados_seriais',
        verbose_name='Cliente Comprador',
    )
    nota_fiscal_saida = models.CharField('NF de Venda', max_length=50, blank=True, null=True)
    data_venda = models.DateTimeField('Data da Venda', null=True, blank=True)
    data_fim_garantia = models.DateField('Data Fim da Garantia', null=True, blank=True)

    # Observações e Histórico de Assistência/RMA
    historico_rma = models.TextField('Histórico de Trocas / RMA', blank=True, null=True)

    class Meta:
        verbose_name = 'Número de Série'
        verbose_name_plural = 'Números de Série'
        ordering = ['-data_entrada', 'numero_serie']

    @property
    def esta_em_garantia(self):
        if self.data_fim_garantia:
            return self.data_fim_garantia >= timezone.now().date()
        return False

    def calcular_data_fim_garantia(self):
        """Calcula o término da garantia com base na data_venda e garantia_meses do produto."""
        if self.data_venda and self.produto and self.produto.garantia_meses:
            venda_date = self.data_venda.date() if hasattr(self.data_venda, 'date') else self.data_venda
            month = venda_date.month - 1 + self.produto.garantia_meses
            year = venda_date.year + (month // 12)
            month = (month % 12) + 1
            max_days = calendar.monthrange(year, month)[1]
            day = min(venda_date.day, max_days)
            return datetime.date(year, month, day)
        return None

    def _sincronizar_estoque_produto(self, produto, localizacao_ids=None):
        if not produto or not produto.controla_numero_serie:
            return
        if apps.is_installed('estoque') and localizacao_ids:
            EstoqueLocalizacao = apps.get_model('estoque', 'EstoqueLocalizacao')
            for loc_id in {lid for lid in localizacao_ids if lid is not None}:
                qtd = produto.numeros_serie.filter(
                    status='DISPONIVEL',
                    localizacao_estoque_id=loc_id,
                ).count()
                if qtd == 0:
                    EstoqueLocalizacao.objects.filter(
                        produto=produto,
                        localizacao_id=loc_id,
                    ).update(quantidade=0)
                else:
                    EstoqueLocalizacao.objects.update_or_create(
                        produto=produto,
                        localizacao_id=loc_id,
                        defaults={'quantidade': qtd},
                    )
        contagem_disponivel = produto.numeros_serie.filter(status='DISPONIVEL').count()
        if produto.estoque_atual != contagem_disponivel:
            produto.estoque_atual = contagem_disponivel
            produto.save(update_fields=['estoque_atual'])

    def save(self, *args, **kwargs):
        if self.numero_serie:
            self.numero_serie = unidecode(self.numero_serie).upper().strip()
        if self.nota_fiscal_entrada:
            self.nota_fiscal_entrada = unidecode(self.nota_fiscal_entrada).upper().strip()
        if self.nota_fiscal_saida:
            self.nota_fiscal_saida = unidecode(self.nota_fiscal_saida).upper().strip()

        # Calcular data de garantia automaticamente quando vendido
        if self.status == 'VENDIDO' and self.data_venda and not self.data_fim_garantia:
            self.data_fim_garantia = self.calcular_data_fim_garantia()

        loc_ids = set()
        if self.pk:
            anterior_loc_id = (
                NumeroSerie.objects.filter(pk=self.pk)
                .values_list('localizacao_estoque_id', flat=True)
                .first()
            )
            if anterior_loc_id:
                loc_ids.add(anterior_loc_id)
        if self.localizacao_estoque_id:
            loc_ids.add(self.localizacao_estoque_id)

        skip_sync = getattr(self, '_skip_sync_estoque', False)
        super().save(*args, **kwargs)
        if not skip_sync:
            self._sincronizar_estoque_produto(self.produto, loc_ids)

    def delete(self, *args, **kwargs):
        produto = self.produto
        loc_id = self.localizacao_estoque_id
        skip_sync = getattr(self, '_skip_sync_estoque', False)
        super().delete(*args, **kwargs)
        if not skip_sync:
            self._sincronizar_estoque_produto(produto, {loc_id} if loc_id else None)

    def __str__(self):
        return f'{self.numero_serie} ({self.produto.nome}) - {self.get_status_display()}'
