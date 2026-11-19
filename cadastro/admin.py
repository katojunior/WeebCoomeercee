from decimal import Decimal
from django.contrib import admin
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Estado, Cidade, Pessoas, Empresa, ExtratoCliente
from .relatorios import ORDENACAO_CAMPOS, consultar_resumo_cliente, exportar_resumo_csv
from ordem_servico.models import EquipamentoCliente, OrdemServico
from vendas.models import Venda
from financeiro.models import TituloFinanceiro


AUDITORIA_FIELDSET = (
    'Auditoria e Configuração',
    {
        'classes': ('collapse',),
        'fields': (
            ('usuario', 'usuario_atualizou'),
            ('data_hora', 'data_hora_atualizada'),
        ),
    },
)


class BaseAdmin(admin.ModelAdmin):
    """Classe base do Admin para preenchimento e controle automático dos campos de auditoria."""
    readonly_fields = ('usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada')

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.usuario and request.user.is_authenticated:
                obj.usuario = request.user.username
        else:
            if request.user.is_authenticated:
                obj.usuario_atualizou = request.user.username
        super().save_model(request, obj, form, change)


@admin.register(Estado)
class EstadoAdmin(BaseAdmin):
    list_display = ('id', 'codigoUf', 'uf', 'estado', 'regiao')
    search_fields = ('uf', 'estado', 'codigoUf')
    list_filter = ('regiao',)

    fieldsets = (
        ('Identificação do Estado', {
            'fields': (
                ('codigoUf', 'uf'),
                'estado',
                'regiao',
            )
        }),
        ('Coordenadas Geográficas', {
            'classes': ('collapse',),
            'fields': (
                ('latitude', 'longitude'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(Cidade)
class CidadeAdmin(BaseAdmin):
    list_display = ('id', 'descricaoCidade', 'uf', 'capital', 'ddd', 'codigoIbge')
    search_fields = ('descricaoCidade', 'descricao_completa', 'codigoIbge')
    list_filter = ('uf', 'capital')
    list_editable = ('capital',)
    readonly_fields = ('descricao_completa', 'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada')

    fieldsets = (
        ('Identificação da Cidade', {
            'fields': (
                'descricaoCidade',
                'uf',
                ('capital', 'ddd'),
                'codigoIbge',
                'descricao_completa',
            )
        }),
        ('Localização e Fuso Horário', {
            'classes': ('collapse',),
            'fields': (
                'fusoHorario',
                ('latitude', 'longitude'),
            )
        }),
        AUDITORIA_FIELDSET,
    )


class EquipamentoClienteInline(admin.TabularInline):
    model = EquipamentoCliente
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    autocomplete_fields = ('marca',)
    fields = ('descricao', 'marca', 'modelo', 'numero_serie', 'ativo')
    show_change_link = True
    verbose_name = 'Equipamento'
    verbose_name_plural = 'Equipamentos do Cliente'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('marca')


class VendaClienteInline(admin.TabularInline):
    model = Venda
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'data_venda',
        'vendedor',
        'status',
        'finalizada',
        'condicao_pagamento',
        'subtotal',
        'desconto',
        'valor_total',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Venda'
    verbose_name_plural = 'Histórico de Vendas (Últimas 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('vendedor').order_by('-data_venda', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(Venda.objects.filter(cliente_id=object_id).order_by('-data_venda', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


class OrdemServicoClienteInline(admin.TabularInline):
    model = OrdemServico
    fk_name = 'cliente'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'data_abertura',
        'equipamento',
        'tecnico',
        'status',
        'finalizada',
        'condicao_pagamento',
        'valor_total',
        'data_conclusao',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Ordem de Serviço'
    verbose_name_plural = 'Histórico de Ordens de Serviço (Últimas 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('equipamento', 'tecnico').order_by('-data_abertura', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(OrdemServico.objects.filter(cliente_id=object_id).order_by('-data_abertura', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


class TituloFinanceiroClienteInline(admin.TabularInline):
    model = TituloFinanceiro
    fk_name = 'pessoa'
    extra = 0
    classes = ('collapse',)
    fields = (
        'id',
        'numero_documento',
        'parcela_numero',
        'parcela_total',
        'origem',
        'data_vencimento',
        'valor_original',
        'valor_pago',
        'saldo_devedor',
        'status',
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    verbose_name = 'Título a Receber'
    verbose_name_plural = 'Contas a Receber / Títulos Financeiros (Últimos 50)'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(tipo='RECEBER').order_by('-data_vencimento', '-id')
        object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
        if object_id:
            top_ids = list(TituloFinanceiro.objects.filter(pessoa_id=object_id, tipo='RECEBER').order_by('-data_vencimento', '-id').values_list('id', flat=True)[:50])
            return qs.filter(id__in=top_ids)
        return qs


@admin.register(Pessoas)
class PessoasAdmin(BaseAdmin):
    list_display = (
        'id', 'razao_nome', 'fantasia_contato', 'tipo_pessoa',
        'funcionario', 'juridica_fisica', 'cnpj_cpf', 'celular', 'email', 'acao_extrato'
    )
    list_filter = ('tipo_pessoa', 'funcionario', 'juridica_fisica', 'codigo_cidade__uf')
    search_fields = ('razao_nome', 'fantasia_contato', 'cnpj_cpf', 'inscricao_rg', 'email', 'celular')
    autocomplete_fields = ('codigo_cidade',)
    inlines = [
        EquipamentoClienteInline,
        VendaClienteInline,
        OrdemServicoClienteInline,
        TituloFinanceiroClienteInline,
    ]
    readonly_fields = BaseAdmin.readonly_fields + (
        'resumo_total_vendas',
        'resumo_total_os',
        'resumo_saldo_devedor',
        'resumo_os_em_aberto',
        'botao_extrato_cliente',
    )

    class Media:
        js = ('cadastro/js/masks.js',)

    fieldsets = (
        ('Identificação Principal', {
            'fields': (
                ('tipo_pessoa', 'funcionario', 'juridica_fisica'),
                'razao_nome',
                'fantasia_contato',
                ('cnpj_cpf', 'inscricao_rg'),
                ('dt_nasc_fund', 'botao_extrato_cliente'),
            )
        }),
        ('Informações de Contato', {
            'fields': (
                ('email', 'celular'),
                ('telefone', 'telefone2'),
            )
        }),
        ('Endereço e Localização', {
            'fields': (
                ('cep', 'codigo_cidade'),
                ('endereco', 'numero'),
                ('bairro', 'complemento'),
                'caixa_postal',
            )
        }),
        ('Resumo Comercial e Financeiro', {
            'classes': ('collapse',),
            'fields': (
                ('resumo_total_vendas', 'resumo_total_os'),
                ('resumo_saldo_devedor', 'resumo_os_em_aberto'),
                ('primeira_compra', 'ultima_compra'),
            )
        }),
        ('Mídia e Observações', {
            'classes': ('collapse',),
            'fields': (
                'foto',
                'obs',
            )
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Total em Compras (Vendas)')
    def resumo_total_vendas(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        total = obj.vendas.aggregate(total=Sum('valor_total'))['total'] or Decimal('0.00')
        return f"R$ {total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    @admin.display(description='Total em Serviços (OS)')
    def resumo_total_os(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        total = obj.ordens_servico_cliente.aggregate(total=Sum('valor_total'))['total'] or Decimal('0.00')
        return f"R$ {total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    @admin.display(description='Saldo Devedor / A Receber')
    def resumo_saldo_devedor(self, obj):
        if not obj or not obj.pk:
            return 'R$ 0,00'
        saldo = obj.titulos_financeiros.filter(
            tipo='RECEBER',
            status__in=['ABERTO', 'PARCIAL']
        ).aggregate(total=Sum('saldo_devedor'))['total'] or Decimal('0.00')
        if saldo > 0:
            return f"⚠️ R$ {saldo:,.2f} EM ABERTO".replace(',', 'X').replace('.', ',').replace('X', '.')
        return '✅ R$ 0,00 (Em dia)'

    @admin.display(description='OSs em Aberto')
    def resumo_os_em_aberto(self, obj):
        if not obj or not obj.pk:
            return '0'
        qtd = obj.ordens_servico_cliente.filter(finalizada=False).count()
        return f"{qtd} ordem(ns) em andamento" if qtd > 0 else "Nenhuma OS pendente"

    @admin.display(description='Resumo / Extrato')
    def botao_extrato_cliente(self, obj):
        if not obj or not obj.pk:
            return 'Salve o cliente para consultar seu resumo de Vendas e OS.'
        url = f"{reverse('admin:cadastro_extratocliente_changelist')}?cliente={obj.pk}&situacao=abertos&ocultar_cancelados=1"
        return format_html(
            '<a href="{}" style="display:inline-block; background:#0f172a; color:#fff; padding:6px 14px; '
            'border-radius:4px; font-weight:700; font-size:12px; text-decoration:none;">'
            '📊 Resumo / Extrato de Vendas e OS'
            '</a>',
            url,
        )

    @admin.display(description='Extrato')
    def acao_extrato(self, obj):
        if not obj or not obj.pk:
            return '-'
        url = f"{reverse('admin:cadastro_extratocliente_changelist')}?cliente={obj.pk}&situacao=abertos&ocultar_cancelados=1"
        return format_html(
            '<a href="{}" style="display:inline-block; background:#0f172a; color:#fff; padding:4px 8px; '
            'border-radius:4px; font-weight:700; font-size:11px; text-decoration:none; white-space:nowrap;">'
            '📊 Resumo'
            '</a>',
            url,
        )


@admin.register(Empresa)
class EmpresaAdmin(BaseAdmin):
    list_display = (
        'id',
        'nome_fantasia',
        'razao_social',
        'cnpj',
        'inscricao_estadual',
        'cidade',
        'telefone',
        'matriz',
        'ativa',
    )
    list_filter = ('ativa', 'matriz', 'regime_tributario', 'cidade__uf')
    search_fields = ('razao_social', 'nome_fantasia', 'cnpj', 'inscricao_estadual', 'email', 'telefone')
    autocomplete_fields = ('cidade',)
    readonly_fields = BaseAdmin.readonly_fields + (
        'codigo_ibge_cidade',
        'codigo_ibge_estado',
        'preview_cabecalho_impressao',
    )

    class Media:
        js = ('cadastro/js/masks.js',)

    fieldsets = (
        ('Identificação Empresarial e Fiscal', {
            'fields': (
                ('matriz', 'ativa', 'regime_tributario'),
                'razao_social',
                'nome_fantasia',
                ('cnpj', 'inscricao_estadual', 'inscricao_municipal'),
                ('cnae', 'data_fundacao', 'responsavel'),
            )
        }),
        ('Endereço e Localização (IBGE)', {
            'fields': (
                ('cep', 'cidade'),
                ('codigo_ibge_cidade', 'codigo_ibge_estado'),
                ('endereco', 'numero'),
                ('bairro', 'complemento', 'caixa_postal'),
            )
        }),
        ('Contatos e Dados para Recebimento', {
            'fields': (
                ('telefone', 'telefone2', 'celular'),
                ('email', 'site'),
                'chave_pix',
            )
        }),
        ('Identidade Visual e Cabeçalhos de Impressão', {
            'fields': (
                'preview_cabecalho_impressao',
                ('logo', 'slogan'),
                'texto_cabecalho_impressao',
                'texto_rodape_impressao',
            )
        }),
        ('Observações Internas', {
            'classes': ('collapse',),
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )

    @admin.display(description='Pré-visualização do Cabeçalho de Impressão')
    def preview_cabecalho_impressao(self, obj):
        if not obj or not obj.pk:
            return 'Salve o cadastro da empresa para visualizar o cabeçalho de impressão.'

        cab = obj.dados_cabecalho_impressao
        logo_html = ''
        if cab.get('logo_url'):
            logo_html = format_html(
                '<img src="{}" alt="Logo" style="max-height:70px; max-width:160px; margin-right:16px; object-fit:contain;" />',
                cab['logo_url'],
            )

        return format_html(
            '<div style="border:1px solid #ccc; border-radius:6px; padding:12px 16px; background:#fff; color:#111; '
            'font-family:Arial, sans-serif; display:flex; align-items:center; max-width:780px;">'
            '{}'
            '<div style="flex:1; line-height:1.45;">'
            '<div style="font-size:16px; font-weight:bold; color:#000;">{}</div>'
            '<div style="font-size:12px; color:#333;">{}</div>'
            '<div style="font-size:12px; color:#333;">{}</div>'
            '<div style="font-size:12px; color:#333;">{}</div>'
            '<div style="font-size:12px; font-weight:600; color:#222;">{}</div>'
            '</div>'
            '</div>',
            logo_html,
            cab['titulo'],
            cab['razao_social'] if cab['razao_social'] != cab['titulo'] else (cab['subtitulo'] or ''),
            cab['documento_formatado'],
            cab['endereco_completo'],
            cab['contatos_formatados'],
        )


@admin.register(ExtratoCliente)
class ExtratoClienteAdmin(admin.ModelAdmin):
    """Tela gerencial consolidada de Vendas e Ordens de Serviço por Cliente, Período e Situação."""

    SITUACAO_LABELS = {
        'abertos': 'Somente Em Aberto (Finalizada = Não)',
        'abertos_ou_financeiro': 'Em Aberto + Pendência Financeira',
        'finalizados': 'Somente Finalizadas (Finalizada = Sim)',
        'todos': 'Todas',
    }

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'buscar-clientes/',
                self.admin_site.admin_view(self.buscar_clientes_view),
                name='cadastro_extratocliente_buscar_clientes',
            ),
        ]
        return custom_urls + urls

    def buscar_clientes_view(self, request):
        termo = (request.GET.get('q') or '').strip()
        qs = Pessoas.objects.all()
        if termo:
            filtros = (
                Q(razao_nome__icontains=termo)
                | Q(fantasia_contato__icontains=termo)
                | Q(cnpj_cpf__icontains=termo)
            )
            if termo.isdigit():
                filtros |= Q(id=int(termo))
            qs = qs.filter(filtros)

        clientes = qs.order_by('razao_nome')[:30]
        results = []
        for c in clientes:
            doc = f" ({c.cnpj_cpf})" if c.cnpj_cpf else ""
            results.append({'id': c.id, 'text': f"{c.razao_nome}{doc}"})
        return JsonResponse({'results': results})

    def changelist_view(self, request, extra_context=None):
        cliente_raw = (request.GET.get('cliente') or '').strip()
        cliente_id = int(cliente_raw) if cliente_raw.isdigit() else None
        data_inicio = (request.GET.get('data_inicio') or '').strip()
        data_fim = (request.GET.get('data_fim') or '').strip()
        situacao = request.GET.get('situacao') or 'abertos'
        if situacao not in self.SITUACAO_LABELS:
            situacao = 'abertos'
        tipo_doc = request.GET.get('tipo_doc') or 'ambos'
        if tipo_doc not in ('ambos', 'vendas', 'ordens'):
            tipo_doc = 'ambos'

        ocultar_raw = request.GET.get('ocultar_cancelados', '1')
        ocultar_cancelados = ocultar_raw not in ('0', 'false', 'False', '')

        ordenar_por = (request.GET.get('ordenar_por') or 'data').strip()
        if ordenar_por not in ORDENACAO_CAMPOS:
            ordenar_por = 'data'
        direcao = (request.GET.get('direcao') or 'desc').strip().lower()
        if direcao not in ('asc', 'desc'):
            direcao = 'desc'

        imprimir_todos = request.GET.get('imprimir_todos') in ('1', 'true', 'True')
        acao = (request.GET.get('acao') or '').strip()
        exportar = (request.GET.get('exportar') or '').strip()
        selected_keys = [k.strip() for k in request.GET.getlist('sel') if k.strip()]

        is_print_mode = imprimir_todos or acao in ('imprimir_resumo', 'imprimir_detalhado')
        selected_for_query = selected_keys if (is_print_mode or exportar == 'csv') and selected_keys else None

        dados = consultar_resumo_cliente(
            cliente_id=cliente_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            situacao=situacao,
            tipo_doc=tipo_doc,
            ocultar_cancelados=ocultar_cancelados,
            ordenar_por=ordenar_por,
            direcao=direcao,
            selected_keys=selected_for_query,
        )

        if exportar == 'csv':
            return exportar_resumo_csv(dados)

        if is_print_mode:
            modo_detalhado = imprimir_todos or acao == 'imprimir_detalhado'
            params_voltar = request.GET.copy()
            for key in ('imprimir_todos', 'acao', 'exportar', 'sel'):
                params_voltar.pop(key, None)
            qs_voltar = params_voltar.urlencode()
            url_voltar = reverse('admin:cadastro_extratocliente_changelist')
            if qs_voltar:
                url_voltar = f'{url_voltar}?{qs_voltar}'

            return render(
                request,
                'admin/cadastro/extratocliente/imprimir_lote.html',
                {
                    'dados': dados,
                    'cabecalho': dados['cabecalho'],
                    'modo_detalhado': modo_detalhado,
                    'situacao_label': self.SITUACAO_LABELS.get(situacao, situacao),
                    'url_voltar': url_voltar,
                },
            )

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Resumo / Extrato Consolidado de Cliente (Vendas e OS)',
            'dados': dados,
            'data_inicio_str': dados['data_inicio'].isoformat() if dados['data_inicio'] else '',
            'data_fim_str': dados['data_fim'].isoformat() if dados['data_fim'] else '',
            'situacao': situacao,
            'tipo_doc': tipo_doc,
            'ocultar_cancelados': ocultar_cancelados,
            'ordenar_por': ordenar_por,
            'direcao': direcao,
            'ordenacao_campos': ORDENACAO_CAMPOS.items(),
            'imprimir_todos': imprimir_todos,
        }
        return render(request, 'admin/cadastro/extratocliente/resumo_cliente.html', context)



