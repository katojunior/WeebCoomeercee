from datetime import date
from decimal import Decimal
from django.contrib import admin, messages
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from cadastro.admin_filters import DateRangeFilter
from cadastro.models import Pessoas, Empresa
from cadastro_produto.models import Produtos
from financeiro.models import ContaBancaria, TituloFinanceiro
from financeiro.utils import CONDICAO_PAGAMENTO_CHOICES
from .models import EquipamentoCliente, OrdemServico, ItemOrdemServico


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


class ItemOrdemServicoInline(admin.TabularInline):
    model = ItemOrdemServico
    extra = 0
    autocomplete_fields = ('produto',)
    fields = ('tipo_item', 'produto', 'descricao_personalizada', 'quantidade', 'valor_unitario', 'valor_total')
    readonly_fields = ('valor_total',)

    def has_add_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.finalizada:
            return False
        return super().has_delete_permission(request, obj)


class ParcelaReceberInline(admin.TabularInline):
    """Exibição das parcelas geradas no Financeiro vinculadas à Ordem de Serviço."""
    model = TituloFinanceiro
    extra = 0
    can_delete = False
    verbose_name = 'Parcela / Título a Receber'
    verbose_name_plural = 'Parcelas Geradas (Financeiro)'
    fields = (
        'parcela_numero',
        'parcela_total',
        'data_vencimento',
        'valor_original',
        'valor_pago',
        'saldo_devedor',
        'status',
        'forma_pagamento_prevista',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EquipamentoCliente)
class EquipamentoClienteAdmin(BaseAdmin):
    list_display = ('id', 'descricao', 'cliente', 'marca', 'modelo', 'numero_serie', 'ativo')
    list_filter = ('ativo', 'marca')
    search_fields = ('descricao', 'modelo', 'numero_serie', 'cliente__razao_nome', 'cliente__cnpj_cpf')
    autocomplete_fields = ('cliente', 'marca')

    fieldsets = (
        ('Identificação do Equipamento', {
            'fields': (
                'cliente',
                'descricao',
                ('marca', 'modelo'),
                'numero_serie',
                'ativo',
            )
        }),
        ('Observações', {
            'fields': ('observacoes',)
        }),
        AUDITORIA_FIELDSET,
    )


@admin.register(OrdemServico)
class OrdemServicoAdmin(BaseAdmin):
    list_display = (
        'id', 'cliente', 'equipamento', 'tecnico', 'status',
        'finalizada', 'data_abertura', 'data_conclusao', 'valor_total', 'acoes_fechamento',
    )
    list_filter = (
        'finalizada',
        'status',
        'condicao_pagamento',
        ('data_abertura', DateRangeFilter),
        'data_conclusao',
        'tecnico',
    )
    search_fields = (
        'id', 'cliente__razao_nome', 'cliente__cnpj_cpf',
        'equipamento__descricao', 'equipamento__numero_serie',
        'numero_nf', 'numero_cupom_fiscal'
    )
    autocomplete_fields = ('cliente',)
    inlines = [ItemOrdemServicoInline, ParcelaReceberInline]
    actions = ['finalizar_e_faturar_ordens', 'reabrir_e_estornar_ordens']
    readonly_fields = (
        'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada',
        'finalizada', 'data_finalizacao', 'botao_fechamento_os',
        'valor_pecas', 'valor_servicos', 'valor_total'
    )

    class Media:
        js = ('ordem_servico/js/os_admin.js',)

    fieldsets = (
        ('Informações da Ordem de Serviço', {
            'fields': (
                ('cliente', 'equipamento'),
                ('tecnico', 'status'),
                ('data_abertura', 'previsao_entrega', 'data_conclusao'),
            )
        }),
        ('Diagnóstico e Laudo Técnico', {
            'fields': (
                'defeito_reclamado',
                'laudo_tecnico',
            )
        }),
        ('Valores e Totais', {
            'classes': ('os-fieldset-bottom',),
            'fields': (
                ('valor_pecas', 'valor_servicos'),
                ('desconto', 'valor_total'),
            )
        }),
        ('Condições de Pagamento e Faturamento', {
            'classes': ('collapse', 'os-fieldset-bottom'),
            'fields': (
                ('condicao_pagamento', 'conta_destino'),
                ('data_primeiro_vencimento', 'numero_parcelas', 'intervalo_dias'),
                ('numero_nf', 'numero_cupom_fiscal'),
            )
        }),
        ('Observações', {
            'classes': ('collapse', 'os-fieldset-bottom'),
            'fields': ('observacoes',)
        }),
        (
            AUDITORIA_FIELDSET[0],
            {
                **AUDITORIA_FIELDSET[1],
                'classes': ('collapse', 'os-fieldset-bottom'),
            },
        ),
        ('Controle e Trava de Fechamento', {
            'classes': ('os-fieldset-bottom', 'os-fieldset-fechamento'),
            'fields': (
                ('finalizada', 'data_finalizacao', 'botao_fechamento_os'),
            )
        }),
    )

    @admin.display(description='Financeiro')
    def status_financeiro_badge(self, obj):
        return obj.status_financeiro

    @admin.display(description='Ação de Fechamento / Impressão')
    def botao_fechamento_os(self, obj):
        if not obj or not obj.pk:
            return mark_safe(
                '<button type="button" class="js-open-finalizar-os-modal" '
                'style="background:#16a34a; color:#fff; border:none; padding:7px 14px; border-radius:4px; '
                'font-weight:700; cursor:pointer; font-size:12px;">'
                '✅ Finalizar / Faturar OS'
                '</button>'
            )
        url_imprimir = reverse('admin:ordem_servico_ordemservico_imprimir', args=[obj.pk])
        if not obj.finalizada:
            url_fin = reverse('admin:ordem_servico_ordemservico_finalizar', args=[obj.pk])
            return format_html(
                '<div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">'
                '<button type="button" class="js-open-finalizar-os-modal" '
                'style="background:#16a34a; color:#fff; border:none; padding:7px 14px; border-radius:4px; '
                'font-weight:700; cursor:pointer; font-size:12px;">'
                '✅ Finalizar / Faturar OS'
                '</button>'
                '<a href="{}" target="_blank" data-print-url="{}" class="js-print-os-link" '
                'style="display:inline-block; background:#2563eb; color:#fff; padding:7px 14px; border-radius:4px; '
                'font-weight:700; font-size:12px; text-decoration:none;">'
                '🖨️ Imprimir OS'
                '</a>'
                '<a href="{}" style="font-size:12px; font-weight:600; text-decoration:underline;">'
                'Abrir tela de fechamento'
                '</a>'
                '</div>',
                url_imprimir,
                url_imprimir,
                url_fin,
            )
        url_reabrir = reverse('admin:ordem_servico_ordemservico_reabrir', args=[obj.pk])
        return format_html(
            '<div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">'
            '<span style="background:#dcfce7; color:#166534; padding:4px 10px; border-radius:12px; '
            'font-weight:700; font-size:12px;">🔒 OS Finalizada ({})</span>'
            '<a href="{}" target="_blank" data-print-url="{}" class="js-print-os-link" '
            'style="display:inline-block; background:#2563eb; color:#fff; padding:6px 14px; border-radius:4px; '
            'font-weight:700; font-size:12px; text-decoration:none;">'
            '🖨️ Imprimir OS'
            '</a>'
            '<a href="{}" onclick="return confirm(\'Deseja realmente reabrir esta OS e estornar os títulos financeiros?\');" '
            'style="display:inline-block; background:#dc2626; color:#fff; padding:6px 12px; border-radius:4px; font-weight:600; '
            'font-size:12px; text-decoration:none;">🔓 Reabrir e Estornar</a>'
            '</div>',
            obj.status_financeiro,
            url_imprimir,
            url_imprimir,
            url_reabrir,
        )

    @admin.display(description='Ações')
    def acoes_fechamento(self, obj):
        if not obj or not obj.pk:
            return '-'
        url_imprimir = reverse('admin:ordem_servico_ordemservico_imprimir', args=[obj.pk])
        if not obj.finalizada:
            url_fin = reverse('admin:ordem_servico_ordemservico_finalizar', args=[obj.pk])
            return format_html(
                '<div style="display:inline-flex; align-items:center; gap:6px; white-space:nowrap;">'
                '<a href="{}" style="display:inline-block; background:#16a34a; color:#fff; padding:4px 9px; '
                'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;">'
                '✅ Finalizar'
                '</a>'
                '<a href="{}" target="_blank" style="display:inline-block; background:#2563eb; color:#fff; padding:4px 9px; '
                'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;" title="Imprimir OS">'
                '🖨️ Imprimir'
                '</a>'
                '</div>',
                url_fin,
                url_imprimir,
            )
        url_reabrir = reverse('admin:ordem_servico_ordemservico_reabrir', args=[obj.pk])
        return format_html(
            '<div style="display:inline-flex; align-items:center; gap:6px; white-space:nowrap;">'
            '<a href="{}" target="_blank" style="display:inline-block; background:#2563eb; color:#fff; padding:4px 9px; '
            'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;" title="Imprimir OS">'
            '🖨️ Imprimir'
            '</a>'
            '<a href="{}" onclick="return confirm(\'Reabrir a OS #{} e estornar seus títulos financeiros?\');" '
            'style="display:inline-block; background:#475569; color:#fff; padding:4px 8px; border-radius:4px; '
            'font-weight:600; font-size:11px; line-height:1.3; text-decoration:none;" title="Clique para reabrir">'
            '🔓 Reabrir'
            '</a>'
            '</div>',
            url_imprimir,
            url_reabrir,
            obj.pk,
        )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.finalizada:
            # Trava 100% dos campos em modo somente leitura
            return [f.name for f in obj._meta.fields] + ['botao_fechamento_os']
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        if obj and obj.finalizada and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'tecnico':
            # Lista apenas funcionários. Se estiver editando uma OS existente cujo técnico histórico
            # não está marcado como funcionário, inclui-o para preservar o histórico.
            object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
            qs = Pessoas.objects.filter(funcionario=True)
            if object_id:
                os_obj = OrdemServico.objects.filter(pk=object_id).first()
                if os_obj and os_obj.tecnico_id:
                    qs = Pessoas.objects.filter(models.Q(funcionario=True) | models.Q(pk=os_obj.tecnico_id))
            kwargs['queryset'] = qs.order_by('razao_nome')

        elif db_field.name == 'equipamento':
            # Filtra apenas os equipamentos do cliente selecionado
            cliente_id = None
            if request:
                if request.method == 'POST':
                    cliente_id = request.POST.get('cliente')
                elif request.resolver_match and 'object_id' in request.resolver_match.kwargs:
                    os_obj = OrdemServico.objects.filter(pk=request.resolver_match.kwargs['object_id']).first()
                    if os_obj and os_obj.cliente_id:
                        cliente_id = os_obj.cliente_id

            if cliente_id:
                kwargs['queryset'] = EquipamentoCliente.objects.filter(
                    cliente_id=cliente_id,
                    ativo=True
                ).order_by('descricao')
            else:
                if request and request.method == 'POST':
                    kwargs['queryset'] = EquipamentoCliente.objects.filter(ativo=True)
                else:
                    kwargs['queryset'] = EquipamentoCliente.objects.none()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.recalcular_totais(salvar=True)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        ordem = form.instance
        ordem.recalcular_totais(salvar=True)

        solicita_finalizar = request.POST.get('_finalizar_os') == '1'
        if (solicita_finalizar or ordem.finalizada) and not ordem.titulos_financeiros.exists():
            quitada_param = None
            if '_os_quitada' in request.POST:
                quitada_param = request.POST.get('_os_quitada') == '1'
            titulos = ordem.gerar_financeiro(
                usuario=request.user.username if request.user.is_authenticated else None,
                quitada=quitada_param,
            )
            situacao_txt = 'QUITADO(S)' if ordem.status_financeiro == 'QUITADO' else 'EM ABERTO'
            self.message_user(
                request,
                f"OS #{ordem.id:06d} finalizada com sucesso! {len(titulos)} parcela(s) gerada(s) no Contas a Receber ({situacao_txt}).",
                level=messages.SUCCESS,
            )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'equipamentos-cliente/<int:cliente_id>/',
                self.admin_site.admin_view(self.get_equipamentos_cliente),
                name='ordem_servico_equipamentos_cliente',
            ),
            path(
                'preco-produto/<int:produto_id>/',
                self.admin_site.admin_view(self.get_preco_produto),
                name='ordem_servico_preco_produto',
            ),
            path(
                '<int:os_id>/finalizar/',
                self.admin_site.admin_view(self.finalizar_os_view),
                name='ordem_servico_ordemservico_finalizar',
            ),
            path(
                '<int:os_id>/reabrir/',
                self.admin_site.admin_view(self.reabrir_os_view),
                name='ordem_servico_ordemservico_reabrir',
            ),
            path(
                '<int:os_id>/imprimir/',
                self.admin_site.admin_view(self.imprimir_os_view),
                name='ordem_servico_ordemservico_imprimir',
            ),
        ]
        return custom_urls + urls

    def imprimir_os_view(self, request, os_id):
        ordem = get_object_or_404(
            OrdemServico.objects.select_related(
                'cliente', 'cliente__codigo_cidade', 'equipamento', 'equipamento__marca', 'tecnico', 'conta_destino'
            ),
            pk=os_id,
        )
        ordem.recalcular_totais(salvar=True)
        itens = list(ordem.itens.select_related('produto', 'equipamento').all())
        titulos = list(ordem.titulos)
        empresa = Empresa.get_principal()
        cabecalho = empresa.dados_cabecalho_impressao if empresa else {}

        context = {
            'ordem': ordem,
            'itens': itens,
            'titulos': titulos,
            'empresa': empresa,
            'cabecalho': cabecalho,
            'vias_range': [1, 2],
        }
        return render(request, 'admin/ordem_servico/ordemservico/imprimir_os.html', context)

    def get_equipamentos_cliente(self, request, cliente_id):
        equipamentos = EquipamentoCliente.objects.filter(
            cliente_id=cliente_id,
            ativo=True
        ).order_by('descricao')
        dados = [{'id': eq.id, 'descricao': str(eq)} for eq in equipamentos]
        return JsonResponse({'equipamentos': dados})

    def get_preco_produto(self, request, produto_id):
        prod = Produtos.objects.filter(pk=produto_id).values('id', 'nome', 'preco_venda').first()
        if not prod:
            return JsonResponse({'preco_venda': '0.00'}, status=404)
        return JsonResponse({
            'id': prod['id'],
            'nome': prod['nome'],
            'preco_venda': str(prod['preco_venda'] or Decimal('0.00')),
        })

    def finalizar_os_view(self, request, os_id):
        ordem = get_object_or_404(OrdemServico.objects.select_related('cliente', 'equipamento', 'conta_destino'), pk=os_id)
        if ordem.finalizada:
            self.message_user(request, f"A OS #{ordem.id:06d} já se encontra finalizada.", level=messages.WARNING)
            return redirect('admin:ordem_servico_ordemservico_change', ordem.pk)

        ordem.recalcular_totais(salvar=True)

        if request.method == 'POST':
            condicao = request.POST.get('condicao_pagamento') or ordem.condicao_pagamento or 'DINHEIRO'
            try:
                num_parcelas = max(1, int(request.POST.get('numero_parcelas') or 1))
            except (TypeError, ValueError):
                num_parcelas = 1

            try:
                intervalo_dias = max(0, int(request.POST.get('intervalo_dias') or 30))
            except (TypeError, ValueError):
                intervalo_dias = 30

            dt_venc_str = request.POST.get('data_primeiro_vencimento')
            try:
                dt_venc = date.fromisoformat(dt_venc_str) if dt_venc_str else timezone.localdate()
            except ValueError:
                dt_venc = timezone.localdate()

            conta_id = request.POST.get('conta_destino')
            conta_obj = ContaBancaria.objects.filter(pk=conta_id).first() if conta_id else None

            desconto_str = (request.POST.get('desconto') or '0').replace(',', '.')
            try:
                desconto_val = max(Decimal('0.00'), Decimal(desconto_str))
            except Exception:
                desconto_val = ordem.desconto or Decimal('0.00')

            quitada = request.POST.get('quitada') == '1'
            numero_nf = (request.POST.get('numero_nf') or '').strip() or None
            numero_cf = (request.POST.get('numero_cupom_fiscal') or '').strip() or None

            titulos = ordem.finalizar_os(
                condicao_pagamento=condicao,
                numero_parcelas=num_parcelas,
                intervalo_dias=intervalo_dias,
                data_primeiro_vencimento=dt_venc,
                conta_destino=conta_obj,
                desconto=desconto_val,
                quitada=quitada,
                numero_nf=numero_nf,
                numero_cupom_fiscal=numero_cf,
                usuario=request.user.username if request.user.is_authenticated else None,
            )
            situacao_txt = 'QUITADO(S) / PAGO(S)' if quitada else 'EM ABERTO'
            self.message_user(
                request,
                f"OS #{ordem.id:06d} finalizada com sucesso! {len(titulos)} título(s) gerado(s) no Contas a Receber como {situacao_txt}.",
                level=messages.SUCCESS,
            )
            return redirect('admin:ordem_servico_ordemservico_change', ordem.pk)

        dt_vencimento = ordem.data_primeiro_vencimento or timezone.localdate()
        default_quitada = (
            ordem.condicao_pagamento in ('DINHEIRO', 'PIX', 'CARTAO_DEBITO')
            and (ordem.numero_parcelas or 1) == 1
        )
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Finalizar e Faturar OS #{ordem.id:06d}',
            'ordem': ordem,
            'condicoes_pagamento': CONDICAO_PAGAMENTO_CHOICES,
            'contas_bancarias': ContaBancaria.objects.filter(ativo=True).order_by('descricao'),
            'data_vencimento_iso': dt_vencimento.isoformat(),
            'default_quitada': default_quitada,
        }
        return render(request, 'admin/ordem_servico/ordemservico/finalizar_os.html', context)

    def reabrir_os_view(self, request, os_id):
        ordem = get_object_or_404(OrdemServico, pk=os_id)
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir ordens de serviço finalizadas.", level=messages.ERROR)
            return redirect('admin:ordem_servico_ordemservico_change', ordem.pk)

        if ordem.finalizada:
            ordem.estornar_financeiro(usuario=request.user.username)
            self.message_user(
                request,
                f"OS #{ordem.id:06d} reaberta e títulos do Contas a Receber estornados com sucesso.",
                level=messages.SUCCESS,
            )
        return redirect('admin:ordem_servico_ordemservico_change', ordem.pk)

    @admin.action(description="Finalizar e Faturar selecionadas (Gerar Financeiro)")
    def finalizar_e_faturar_ordens(self, request, queryset):
        abertas = queryset.filter(finalizada=False)
        if abertas.count() == 1:
            return redirect('admin:ordem_servico_ordemservico_finalizar', abertas.first().pk)
        count = 0
        for ordem in abertas:
            ordem.gerar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Ordem(ns) de Serviço finalizada(s) e faturada(s) no Financeiro com sucesso.")

    @admin.action(description="Reabrir e Estornar Financeiro selecionadas (Desbloquear)")
    def reabrir_e_estornar_ordens(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir ordens de serviço finalizadas.", level=messages.ERROR)
            return
        count = 0
        for ordem in queryset.filter(finalizada=True):
            ordem.estornar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Ordem(ns) de Serviço reaberta(s) e financeiro estornado com sucesso.")


@admin.register(ItemOrdemServico)
class ItemOrdemServicoAdmin(BaseAdmin):
    list_display = ('id', 'ordem', 'tipo_item', 'produto', 'quantidade', 'valor_unitario', 'valor_total')
    list_filter = ('tipo_item',)
    search_fields = ('ordem__id', 'produto__nome', 'descricao_personalizada')
    autocomplete_fields = ('ordem', 'produto', 'equipamento')
