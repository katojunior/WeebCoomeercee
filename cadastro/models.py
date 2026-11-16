from django.contrib import admin
from django.db import models
from django.utils import timezone
from stdimage import StdImageField
from unidecode import unidecode
import uuid

from .validators import (
    formatar_cep,
    formatar_cpf_cnpj,
    formatar_telefone,
    validar_cep,
    validar_consistencia_pessoa,
    validar_cpf_cnpj,
)


def get_file_path(_instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'
    return filename


JURIDICA_FISICA_CHOICES = (
    (0, 'JURÍDICA'),
    (1, 'FÍSICA'),
)

TIPO_PESSOA_CHOICES = (
    (0, 'CLIENTE'),
    (1, 'FORNECEDOR'),
    (2, 'AMBOS'),    
)
TIPO_CHOICES = TIPO_PESSOA_CHOICES


STATUS_FINANCEIRO = (
    ('EM ABERTO', 'EM ABERTO'),
    ('QUITADO', 'QUITADO'),
)

REGIAO_CHOICES = (
    ('NORTE', 'Norte'),
    ('NORDESTE', 'Nordeste'),
    ('CENTRO-OESTE', 'Centro-Oeste'),
    ('SUDESTE', 'Sudeste'),
    ('SUL', 'Sul'),
)


class Base(models.Model):
    data_hora = models.DateTimeField('Data de Cadastro', auto_now_add=True, null=True, blank=True)
    data_hora_atualizada = models.DateTimeField('Ultima Ateração', auto_now=True, null=True, blank=True)
    usuario = models.CharField('Usuário', max_length=50, null=True, blank=True)
    usuario_atualizou = models.CharField('Usuário Atualizou', max_length=50, null=True, blank=True)
    class Meta:
        abstract = True

class Estado(Base):
    codigoUf         = models.IntegerField('Código', unique=True, null=True, blank=True)
    uf               = models.CharField      ('UF', unique=True,   max_length= 2)
    estado           = models.CharField      ('Estado', max_length=50                 )
    latitude         = models.DecimalField   ('Latitude' , max_digits=12, decimal_places=8, null=True, blank=True)
    longitude        = models.DecimalField   ('Longitude', max_digits=12, decimal_places=8, null=True, blank=True)
    regiao           = models.CharField      ('Região', max_length=50 , choices=REGIAO_CHOICES, null=True, blank=True)
    class Meta:
        verbose_name = 'Estado'
        verbose_name_plural = 'Estados'
        ordering = ['estado']
    def save(self, *args, **kwargs):
        self.uf = unidecode(self.uf).upper() if self.uf else None
        self.estado = unidecode(self.estado).upper() if self.estado else None
        self.regiao = unidecode(self.regiao).upper().strip() if self.regiao else None
        super().save(*args, **kwargs)
    def __str__(self):
        return self.uf

class Cidade(Base):
    descricaoCidade    = models.CharField   ('Cidade',             max_length=100, null=True, blank=True)
    descricao_completa = models.CharField   ('Descrição Completa', max_length=100, null=True, blank=True)
    uf                 = models.ForeignKey  ('cadastro.Estado',    verbose_name='UF', on_delete=models.RESTRICT)
    latitude           = models.DecimalField('Latitude' ,          max_digits=12, decimal_places=8, null=True, blank=True)
    longitude          = models.DecimalField('Longitude',          max_digits=12, decimal_places=8, null=True, blank=True)
    capital            = models.BooleanField('Capital?',           default = False)
    ddd                = models.CharField   ('DDD',                max_length=2, null=True, blank=True)
    fusoHorario        = models.CharField   ('Fuso Horário',       max_length=50, null=True, blank=True)
    codigoIbge         = models.CharField   ('Codigo Ibge',         max_length=50, unique=True, null=True, blank=True)
    class Meta:
        verbose_name = 'Cidade'
        verbose_name_plural = 'Cidades'
        ordering = ['descricaoCidade']
    def save(self, *args, **kwargs):
        # Calcular a descrição completa antes de salvar
        if self.descricaoCidade and self.uf:
            self.descricao_completa = f'{self.descricaoCidade} / {self.uf}'
        self.descricaoCidade = unidecode(self.descricaoCidade).upper() if self.descricaoCidade else None
        self.descricao_completa = unidecode(self.descricao_completa).upper() if self.descricao_completa else None
        self.codigoIbge = self.codigoIbge.strip() or None if self.codigoIbge else None
        super().save(*args, **kwargs)
    def __str__(self):
        return self.descricao_completa or ''


class Pessoas(Base):
    juridica_fisica = models.SmallIntegerField('Jurídica/Física', choices=JURIDICA_FISICA_CHOICES)
    tipo_pessoa = models.SmallIntegerField('Tipo Pessoa', choices=TIPO_PESSOA_CHOICES, default=0)
    funcionario = models.BooleanField('Funcionário?', default=False)
    inscricao_rg = models.CharField('I.E./RG', max_length=15, blank=True, null=True)
    cnpj_cpf = models.CharField('CNPJ/CPF', max_length=18, unique=True, blank=True, null=True, validators=[validar_cpf_cnpj])
    razao_nome = models.CharField('Razão Social/Nome', max_length=100)
    fantasia_contato = models.CharField('Nome Fantasia/Contato', max_length=100, blank=True, null=True)
    endereco = models.CharField('Endereço', max_length=100, blank=True, null=True)
    numero = models.CharField('Número', max_length=18, blank=True, null=True)
    complemento = models.CharField('Complemento', max_length=50, blank=True, null=True)
    bairro = models.CharField('Bairro', max_length=50, blank=True, null=True)
    cep = models.CharField('Cep', max_length=10, blank=True, null=True, validators=[validar_cep])
    codigo_cidade = models.ForeignKey('cadastro.Cidade', verbose_name='Cidade', on_delete=models.RESTRICT, blank=True, null=True)
    caixa_postal = models.CharField('Caixa Postal', max_length=18, blank=True, null=True)
    primeira_compra = models.DateField ('Primeira Compra', null=True, blank=True)
    ultima_compra = models.DateField ('Ultima Compra', null=True, blank=True)
    celular = models.CharField('Celular', max_length=15, blank=True, null=True)
    telefone = models.CharField('Telefone', max_length=15, blank=True, null=True)
    telefone2 = models.CharField('Telefone2', max_length=15, blank=True, null=True)
    dt_nasc_fund = models.DateField('Data Nascimento/Fundação.', blank=True, null=True)
    email = models.EmailField('E-mail', max_length=100, blank=True, null=True)
    obs = models.TextField('Obs', blank=True, null=True)
    foto = StdImageField('Foto', upload_to=get_file_path, null=True, blank=True, variations={'thumb': {'width': 480, 'height': 480, 'crop': True}})

    @property
    def codigo_tipo(self):
        return self.tipo_pessoa

    @codigo_tipo.setter
    def codigo_tipo(self, value):
        self.tipo_pessoa = value

    @property
    def cnpj_cfp(self):
        return self.cnpj_cpf

    @cnpj_cfp.setter
    def cnpj_cfp(self, value):
        self.cnpj_cpf = value

    class Meta:
        verbose_name        = 'Cliente/Fornecedor'
        verbose_name_plural = 'Clientes/Fornecedores'
        ordering = ['razao_nome']

    def clean(self):
        super().clean()
        validar_consistencia_pessoa(self.juridica_fisica, self.cnpj_cpf)

    def save(self, *args, **kwargs):
        self.cnpj_cpf = formatar_cpf_cnpj(self.cnpj_cpf)
        self.cep = formatar_cep(self.cep)
        self.celular = formatar_telefone(self.celular)
        self.telefone = formatar_telefone(self.telefone)
        self.telefone2 = formatar_telefone(self.telefone2)
        self.razao_nome = unidecode(self.razao_nome).upper() if self.razao_nome else None
        self.fantasia_contato = unidecode(self.fantasia_contato).upper() if self.fantasia_contato else None
        self.endereco = unidecode(self.endereco).upper() if self.endereco else None
        self.numero = unidecode(self.numero).upper() if self.numero else None
        self.complemento = unidecode(self.complemento).upper() if self.complemento else None
        self.bairro = unidecode(self.bairro).upper() if self.bairro else None
        self.caixa_postal = unidecode(self.caixa_postal).upper() if self.caixa_postal else None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.razao_nome or ''


# Aliases para compatibilidade
Pessoa = Pessoas
Cliente = Pessoas

