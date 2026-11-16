import re

from django.core.exceptions import ValidationError
from django.db import models
from unidecode import unidecode

from cadastro.models import Base


TIPO_OPERACAO_CFOP_CHOICES = (
    ('ENTRADA', 'Entrada'),
    ('SAIDA', 'Saída'),
)


def normalizar_codigo_fiscal(valor):
    """Remove pontos, traços, barras e espaços de códigos fiscais."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return re.sub(r'[.\-/\s]', '', texto)


def validar_ncm(valor):
    """Valida código NCM com exatamente 8 dígitos numéricos."""
    codigo = normalizar_codigo_fiscal(valor)
    if not codigo:
        return
    if not re.fullmatch(r'\d{8}', codigo):
        raise ValidationError('NCM deve conter exatamente 8 dígitos numéricos (ex: 84717040).')


def validar_cest(valor):
    """Valida código CEST com exatamente 7 dígitos numéricos."""
    codigo = normalizar_codigo_fiscal(valor)
    if not codigo:
        return
    if not re.fullmatch(r'\d{7}', codigo):
        raise ValidationError('CEST deve conter exatamente 7 dígitos numéricos (ex: 2103200).')


def validar_cfop(valor):
    """Valida código CFOP com 4 dígitos iniciados por grupo válido (1, 2, 3, 5, 6 ou 7)."""
    codigo = normalizar_codigo_fiscal(valor)
    if not codigo:
        return
    if not re.fullmatch(r'[123567]\d{3}', codigo):
        raise ValidationError('CFOP deve conter 4 dígitos numéricos iniciados por 1, 2, 3, 5, 6 ou 7 (ex: 5102).')


class Ncm(Base):
    """Tabela de referência da Nomenclatura Comum do Mercosul (NCM)."""

    codigo = models.CharField(
        'Código NCM',
        max_length=10,
        unique=True,
        validators=[validar_ncm],
        help_text='8 dígitos numéricos (aceita pontuação na entrada, ex: 8471.70.40)',
    )
    descricao = models.CharField('Descrição', max_length=255)
    aliquota_ipi = models.DecimalField(
        'Alíquota IPI (%)',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'NCM'
        verbose_name_plural = 'NCMs'
        ordering = ['codigo']

    @property
    def codigo_formatado(self):
        if self.codigo and len(self.codigo) == 8:
            return f'{self.codigo[:4]}.{self.codigo[4:6]}.{self.codigo[6:]}'
        return self.codigo or ''

    def save(self, *args, **kwargs):
        if self.codigo:
            self.codigo = normalizar_codigo_fiscal(self.codigo)
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo_formatado} - {self.descricao}'


class Cest(Base):
    """Tabela de referência do Código Especificador da Substituição Tributária (CEST)."""

    codigo = models.CharField(
        'Código CEST',
        max_length=9,
        unique=True,
        validators=[validar_cest],
        help_text='7 dígitos numéricos (aceita pontuação na entrada, ex: 21.032.00)',
    )
    descricao = models.CharField('Descrição', max_length=255)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'CEST'
        verbose_name_plural = 'CESTs'
        ordering = ['codigo']

    @property
    def codigo_formatado(self):
        if self.codigo and len(self.codigo) == 7:
            return f'{self.codigo[:2]}.{self.codigo[2:5]}.{self.codigo[5:]}'
        return self.codigo or ''

    def save(self, *args, **kwargs):
        if self.codigo:
            self.codigo = normalizar_codigo_fiscal(self.codigo)
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo_formatado} - {self.descricao}'


class Cfop(Base):
    """Tabela de referência do Código Fiscal de Operações e Prestações (CFOP)."""

    codigo = models.CharField(
        'Código CFOP',
        max_length=4,
        unique=True,
        validators=[validar_cfop],
        help_text='4 dígitos numéricos (ex: 5102, 5405, 6102)',
    )
    descricao = models.CharField('Descrição / Natureza da Operação', max_length=255)
    tipo_operacao = models.CharField(
        'Tipo de Operação',
        max_length=10,
        choices=TIPO_OPERACAO_CFOP_CHOICES,
        default='SAIDA',
    )
    movimenta_estoque = models.BooleanField('Movimenta Estoque?', default=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'CFOP'
        verbose_name_plural = 'CFOPs'
        ordering = ['codigo']

    def save(self, *args, **kwargs):
        if self.codigo:
            self.codigo = normalizar_codigo_fiscal(self.codigo)
        if self.descricao:
            self.descricao = unidecode(self.descricao).upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo} - {self.descricao} ({self.get_tipo_operacao_display()})'
