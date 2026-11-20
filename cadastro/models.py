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

REGIME_TRIBUTARIO_CHOICES = (
    (1, '1 - Simples Nacional'),
    (2, '2 - Simples Nacional (Excesso de Sublimite)'),
    (3, '3 - Regime Normal (Lucro Presumido / Real)'),
    (4, '4 - Microempreendedor Individual (MEI)'),
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


class ExtratoCliente(Pessoas):
    """Proxy model para tela de Resumo / Extrato Consolidado de Vendas e OS por Cliente."""

    class Meta:
        proxy = True
        verbose_name = 'Resumo / Extrato de Cliente (Vendas e OS)'
        verbose_name_plural = 'Resumo / Extrato de Clientes (Vendas e OS)'


class Empresa(Base):
    """
    Cadastro centralizado da Empresa (Emitente / Matriz / Filial).
    Utilizado para cabeçalhos de impressão (OS, Vendas, Orçamentos, Recibos, Relatórios),
    parametrização fiscal e identificação institucional em todo o sistema.
    """

    razao_social = models.CharField('Razão Social', max_length=150)
    nome_fantasia = models.CharField('Nome Fantasia', max_length=150, blank=True, null=True)
    cnpj = models.CharField(
        'CNPJ / CPF',
        max_length=18,
        unique=True,
        blank=True,
        null=True,
        validators=[validar_cpf_cnpj],
    )
    inscricao_estadual = models.CharField('Inscrição Estadual (I.E.)', max_length=25, blank=True, null=True)
    inscricao_municipal = models.CharField('Inscrição Municipal (I.M.)', max_length=25, blank=True, null=True)
    cnae = models.CharField('CNAE Principal', max_length=15, blank=True, null=True)
    regime_tributario = models.SmallIntegerField(
        'Regime Tributário (CRT)',
        choices=REGIME_TRIBUTARIO_CHOICES,
        default=1,
    )

    endereco = models.CharField('Logradouro / Endereço', max_length=150, blank=True, null=True)
    numero = models.CharField('Número', max_length=20, blank=True, null=True)
    complemento = models.CharField('Complemento', max_length=80, blank=True, null=True)
    bairro = models.CharField('Bairro', max_length=80, blank=True, null=True)
    cep = models.CharField('CEP', max_length=10, blank=True, null=True, validators=[validar_cep])
    cidade = models.ForeignKey(
        'cadastro.Cidade',
        verbose_name='Cidade',
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name='empresas',
    )
    caixa_postal = models.CharField('Caixa Postal', max_length=20, blank=True, null=True)

    telefone = models.CharField('Telefone Principal', max_length=15, blank=True, null=True)
    telefone2 = models.CharField('Telefone Secundário', max_length=15, blank=True, null=True)
    celular = models.CharField('Celular / WhatsApp', max_length=15, blank=True, null=True)
    email = models.EmailField('E-mail', max_length=120, blank=True, null=True)
    site = models.URLField('Site / Página Web', max_length=150, blank=True, null=True)
    chave_pix = models.CharField('Chave PIX (Para Impressão/Recibos)', max_length=120, blank=True, null=True)
    responsavel = models.CharField('Responsável / Proprietário', max_length=100, blank=True, null=True)
    data_fundacao = models.DateField('Data de Fundação', blank=True, null=True)

    slogan = models.CharField(
        'Slogan / Subtítulo de Impressão',
        max_length=150,
        blank=True,
        null=True,
        help_text='Frase curta ou especialidade exibida abaixo do Nome Fantasia nos cabeçalhos.',
    )
    logo = StdImageField(
        'Logotipo (Impressão e Sistema)',
        upload_to=get_file_path,
        null=True,
        blank=True,
        variations={
            'header': {'width': 320, 'height': 120, 'crop': False},
            'thumb': {'width': 160, 'height': 160, 'crop': False},
        },
    )
    texto_cabecalho_impressao = models.TextField(
        'Texto Adicional de Cabeçalho',
        blank=True,
        null=True,
        help_text='Informações adicionais exibidas no cabeçalho de impressões (OS, Vendas, Orçamentos).',
    )
    texto_rodape_impressao = models.TextField(
        'Texto de Rodapé / Termos de Garantia',
        blank=True,
        null=True,
        help_text='Mensagem padrão exibida no rodapé de impressões (termos de garantia, avisos, etc.).',
    )
    observacoes = models.TextField('Observações Internas', blank=True, null=True)

    matriz = models.BooleanField(
        'Matriz / Principal?',
        default=True,
        help_text='Define como empresa principal padrão para cabeçalhos de impressão e documentos.',
    )
    bloquear_fechamento_sem_estoque = models.BooleanField(
        'Bloquear Venda/OS sem Estoque?',
        default=False,
        help_text=(
            'Quando ativo, impede finalizar Vendas ou Ordens de Serviço caso algum produto com '
            'controle de estoque não possua saldo suficiente.'
        ),
    )
    ativa = models.BooleanField('Ativa?', default=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['-matriz', 'razao_social']

    # --- Aliases legados do Firebird para retrocompatibilidade ---
    @property
    def razao_empresa(self):
        return self.razao_social

    @razao_empresa.setter
    def razao_empresa(self, value):
        self.razao_social = value

    @property
    def fantasia_empresa(self):
        return self.nome_fantasia

    @fantasia_empresa.setter
    def fantasia_empresa(self, value):
        self.nome_fantasia = value

    @property
    def cnpj_empresa(self):
        return self.cnpj

    @cnpj_empresa.setter
    def cnpj_empresa(self, value):
        self.cnpj = value

    @property
    def inscricao_empresa(self):
        return self.inscricao_estadual

    @inscricao_empresa.setter
    def inscricao_empresa(self, value):
        self.inscricao_estadual = value

    @property
    def endereco_empresa(self):
        return self.endereco

    @endereco_empresa.setter
    def endereco_empresa(self, value):
        self.endereco = value

    @property
    def numero_emp(self):
        return self.numero

    @numero_emp.setter
    def numero_emp(self, value):
        self.numero = value

    @property
    def bairro_empresa(self):
        return self.bairro

    @bairro_empresa.setter
    def bairro_empresa(self, value):
        self.bairro = value

    @property
    def cep_empresa(self):
        return self.cep

    @cep_empresa.setter
    def cep_empresa(self, value):
        self.cep = value

    @property
    def caixa_postal_empresa(self):
        return self.caixa_postal

    @caixa_postal_empresa.setter
    def caixa_postal_empresa(self, value):
        self.caixa_postal = value

    @property
    def dt_fund_empresa(self):
        return self.data_fundacao

    @dt_fund_empresa.setter
    def dt_fund_empresa(self, value):
        self.data_fundacao = value

    # --- Propriedades Utilitárias e de Impressão ---
    @property
    def nome_exibicao(self):
        """Retorna o Nome Fantasia se preenchido, ou a Razão Social."""
        return self.nome_fantasia or self.razao_social or ''

    @property
    def uf_sigla(self):
        if self.cidade_id and self.cidade and self.cidade.uf_id:
            return self.cidade.uf.uf
        return ''

    @property
    def cidade_uf(self):
        if self.cidade_id and self.cidade:
            uf = self.uf_sigla
            return f"{self.cidade.descricaoCidade}/{uf}" if uf else (self.cidade.descricaoCidade or '')
        return ''

    @property
    def codigo_ibge_cidade(self):
        if self.cidade_id and self.cidade:
            return self.cidade.codigoIbge or ''
        return ''

    @property
    def codigo_ibge_estado(self):
        if self.cidade_id and self.cidade and self.cidade.uf_id and self.cidade.uf.codigoUf:
            return str(self.cidade.uf.codigoUf)
        return ''

    @property
    def endereco_completo(self):
        """Retorna o endereço completo formatado em uma linha para cabeçalhos de impressão."""
        partes = []
        if self.endereco:
            logradouro = self.endereco
            if self.numero:
                logradouro = f"{logradouro}, Nº {self.numero}"
            if self.complemento:
                logradouro = f"{logradouro} ({self.complemento})"
            partes.append(logradouro)
        elif self.numero:
            partes.append(f"Nº {self.numero}")

        if self.bairro:
            partes.append(self.bairro)
        if self.cidade_uf:
            partes.append(self.cidade_uf)
        if self.cep:
            partes.append(f"CEP: {self.cep}")
        if self.caixa_postal:
            partes.append(f"Cx. Postal: {self.caixa_postal}")
        return ' - '.join(partes)

    @property
    def documento_formatado(self):
        """Retorna CNPJ e Inscrições formatados para exibição no cabeçalho."""
        docs = []
        if self.cnpj:
            label = 'CPF' if len(self.cnpj) <= 14 else 'CNPJ'
            docs.append(f"{label}: {self.cnpj}")
        if self.inscricao_estadual:
            docs.append(f"I.E.: {self.inscricao_estadual}")
        if self.inscricao_municipal:
            docs.append(f"I.M.: {self.inscricao_municipal}")
        return ' | '.join(docs)

    @property
    def contatos_formatados(self):
        """Retorna telefones, celular/WhatsApp, e-mail e site agrupados para cabeçalho de impressão."""
        fones = [f for f in (self.telefone, self.telefone2, self.celular) if f]
        blocos = []
        if fones:
            blocos.append('Fone: ' + ' / '.join(fones))
        if self.email:
            blocos.append(f"E-mail: {self.email}")
        if self.site:
            blocos.append(f"Site: {self.site}")
        return ' | '.join(blocos)

    @property
    def dados_cabecalho_impressao(self):
        """Dicionário pronto para uso em templates de impressão, relatórios PDF/HTML e APIs."""
        logo_url = None
        if self.logo:
            try:
                logo_url = self.logo.header.url if hasattr(self.logo, 'header') else self.logo.url
            except Exception:
                logo_url = None

        return {
            'id': self.id,
            'titulo': self.nome_exibicao,
            'subtitulo': self.slogan or '',
            'razao_social': self.razao_social or '',
            'nome_fantasia': self.nome_fantasia or '',
            'cnpj': self.cnpj or '',
            'inscricao_estadual': self.inscricao_estadual or '',
            'inscricao_municipal': self.inscricao_municipal or '',
            'documento_formatado': self.documento_formatado,
            'endereco': self.endereco or '',
            'numero': self.numero or '',
            'complemento': self.complemento or '',
            'bairro': self.bairro or '',
            'cep': self.cep or '',
            'cidade': self.cidade.descricaoCidade if (self.cidade_id and self.cidade) else '',
            'uf': self.uf_sigla,
            'cidade_uf': self.cidade_uf,
            'codigo_ibge_cidade': self.codigo_ibge_cidade,
            'codigo_ibge_estado': self.codigo_ibge_estado,
            'endereco_completo': self.endereco_completo,
            'telefone': self.telefone or '',
            'telefone2': self.telefone2 or '',
            'celular': self.celular or '',
            'email': self.email or '',
            'site': self.site or '',
            'chave_pix': self.chave_pix or '',
            'contatos_formatados': self.contatos_formatados,
            'logo_url': logo_url,
            'texto_cabecalho': self.texto_cabecalho_impressao or '',
            'texto_rodape': self.texto_rodape_impressao or '',
        }

    @classmethod
    def get_principal(cls):
        """Retorna a empresa principal/matriz ativa (ou a primeira cadastrada) para cabeçalhos."""
        return (
            cls.objects.select_related('cidade', 'cidade__uf')
            .filter(ativa=True)
            .order_by('-matriz', 'id')
            .first()
            or cls.objects.select_related('cidade', 'cidade__uf').order_by('-matriz', 'id').first()
        )

    def save(self, *args, **kwargs):
        self.cnpj = formatar_cpf_cnpj(self.cnpj)
        self.cep = formatar_cep(self.cep)
        self.telefone = formatar_telefone(self.telefone)
        self.telefone2 = formatar_telefone(self.telefone2)
        self.celular = formatar_telefone(self.celular)

        self.razao_social = unidecode(self.razao_social).upper().strip() if self.razao_social else None
        self.nome_fantasia = unidecode(self.nome_fantasia).upper().strip() if self.nome_fantasia else None
        self.inscricao_estadual = unidecode(self.inscricao_estadual).upper().strip() if self.inscricao_estadual else None
        self.inscricao_municipal = unidecode(self.inscricao_municipal).upper().strip() if self.inscricao_municipal else None
        self.cnae = unidecode(self.cnae).upper().strip() if self.cnae else None
        self.endereco = unidecode(self.endereco).upper().strip() if self.endereco else None
        self.numero = unidecode(self.numero).upper().strip() if self.numero else None
        self.complemento = unidecode(self.complemento).upper().strip() if self.complemento else None
        self.bairro = unidecode(self.bairro).upper().strip() if self.bairro else None
        self.caixa_postal = unidecode(self.caixa_postal).upper().strip() if self.caixa_postal else None
        self.responsavel = unidecode(self.responsavel).upper().strip() if self.responsavel else None
        self.email = self.email.strip().lower() if self.email else None

        super().save(*args, **kwargs)
        if self.matriz and self.pk:
            Empresa.objects.filter(matriz=True).exclude(pk=self.pk).update(matriz=False)

    def __str__(self):
        return self.nome_fantasia or self.razao_social or ''


