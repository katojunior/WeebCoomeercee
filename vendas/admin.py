from datetime import date
from decimal import Decimal
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
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
from estoque.models import MovimentacaoEstoque
from financeiro.models import ContaBancaria, TituloFinanceiro
from financeiro.utils import CONDICAO_PAGAMENTO_CHOICES
from .models import Venda, ItemVenda


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


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    autocomplete_fields = ('produto', 'numeros_serie')
    fields = ('sequencia', 'produto', 'quantidade', 'valor_unitario', 'desconto_unitario', 'valor_total', 'numeros_serie')
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
    """Exibição das parcelas geradas no Financeiro vinculadas à Venda."""
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


class MovimentacaoEstoqueVendaInline(admin.TabularInline):
    """Exibição das movimentações de estoque geradas a partir da Venda."""
    model = MovimentacaoEstoque
    extra = 0
    can_delete = False
    verbose_name = 'Movimentação de Estoque'
    verbose_name_plural = 'Movimentações de Estoque (Kardex)'
    fields = (
        'data_hora',
        'tipo',
        'origem',
        'produto',
        'quantidade',
        'saldo_anterior_produto',
        'saldo_posterior_produto',
        'documento_referencia',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Venda)
class VendaAdmin(BaseAdmin):
    list_display = (
        'id', 'cliente', 'vendedor', 'status', 'finalizada', 'condicao_pagamento',
        'status_financeiro_badge', 'subtotal', 'desconto', 'valor_total', 'data_venda',
        'acoes_fechamento',
    )
    list_filter = (
        'finalizada',
        'status',
        'condicao_pagamento',
        ('data_venda', DateRangeFilter),
        'vendedor',
    )
    search_fields = (
        'id', 'cliente__razao_nome', 'cliente__cnpj_cpf',
        'numero_nf', 'numero_cupom_fiscal'
    )
    autocomplete_fields = ('cliente',)
    inlines = [ItemVendaInline, ParcelaReceberInline, MovimentacaoEstoqueVendaInline]
    actions = ['finalizar_e_faturar_vendas', 'reabrir_e_estornar_vendas']
    readonly_fields = (
        'usuario', 'usuario_atualizou', 'data_hora', 'data_hora_atualizada',
        'finalizada', 'data_finalizacao', 'botao_fechamento_venda',
        'subtotal', 'valor_total'
    )

    class Media:
        js = ('vendas/js/venda_admin.js',)

    fieldsets = (
        ('Identificação da Venda', {
            'fields': (
                ('cliente', 'vendedor'),
                ('status', 'data_venda'),
            )
        }),
        ('Valores e Totais', {
            'classes': ('venda-fieldset-bottom',),
            'fields': (
                ('subtotal', 'desconto', 'valor_total'),
            )
        }),
        ('Condições de Pagamento e Faturamento', {
            'classes': ('collapse', 'venda-fieldset-bottom'),
            'fields': (
                ('condicao_pagamento', 'conta_destino'),
                ('data_primeiro_vencimento', 'numero_parcelas', 'intervalo_dias'),
                ('numero_nf', 'numero_cupom_fiscal'),
            )
        }),
        ('Observações', {
            'classes': ('collapse', 'venda-fieldset-bottom'),
            'fields': ('observacoes',)
        }),
        (
            AUDITORIA_FIELDSET[0],
            {
                **AUDITORIA_FIELDSET[1],
                'classes': ('collapse', 'venda-fieldset-bottom'),
            },
        ),
        ('Controle e Trava de Fechamento', {
            'classes': ('venda-fieldset-bottom', 'venda-fieldset-fechamento'),
            'fields': (
                ('finalizada', 'data_finalizacao', 'botao_fechamento_venda'),
            )
        }),
    )

    @admin.display(description='Financeiro')
    def status_financeiro_badge(self, obj):
        return obj.status_financeiro

    @admin.display(description='Ação de Fechamento / Impressão')
    def botao_fechamento_venda(self, obj):
        if not obj or not obj.pk:
            return mark_safe(
                '<button type="button" class="js-open-finalizar-venda-modal" '
                'style="background:#16a34a; color:#fff; border:none; padding:7px 14px; border-radius:4px; '
                'font-weight:700; cursor:pointer; font-size:12px;">'
                '✅ Finalizar / Faturar Venda'
                '</button>'
            )
        url_imprimir = reverse('admin:vendas_venda_imprimir', args=[obj.pk])
        if not obj.finalizada:
            url_fin = reverse('admin:vendas_venda_finalizar', args=[obj.pk])
            return format_html(
                '<div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">'
                '<button type="button" class="js-open-finalizar-venda-modal" '
                'style="background:#16a34a; color:#fff; border:none; padding:7px 14px; border-radius:4px; '
                'font-weight:700; cursor:pointer; font-size:12px;">'
                '✅ Finalizar / Faturar Venda'
                '</button>'
                '<a href="{}" target="_blank" data-print-url="{}" class="js-print-venda-link" '
                'style="display:inline-block; background:#2563eb; color:#fff; padding:7px 14px; border-radius:4px; '
                'font-weight:700; font-size:12px; text-decoration:none;">'
                '🖨️ Imprimir Venda'
                '</a>'
                '<a href="{}" style="font-size:12px; font-weight:600; text-decoration:underline;">'
                'Abrir tela de fechamento'
                '</a>'
                '</div>',
                url_imprimir,
                url_imprimir,
                url_fin,
            )
        url_reabrir = reverse('admin:vendas_venda_reabrir', args=[obj.pk])
        return format_html(
            '<div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">'
            '<span style="background:#dcfce7; color:#166534; padding:4px 10px; border-radius:12px; '
            'font-weight:700; font-size:12px;">🔒 Venda Finalizada ({})</span>'
            '<a href="{}" target="_blank" data-print-url="{}" class="js-print-venda-link" '
            'style="display:inline-block; background:#2563eb; color:#fff; padding:6px 14px; border-radius:4px; '
            'font-weight:700; font-size:12px; text-decoration:none;">'
            '🖨️ Imprimir Venda'
            '</a>'
            '<a href="{}" onclick="return confirm(\'Deseja realmente reabrir esta Venda e estornar os títulos financeiros?\');" '
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
        url_imprimir = reverse('admin:vendas_venda_imprimir', args=[obj.pk])
        if not obj.finalizada:
            url_fin = reverse('admin:vendas_venda_finalizar', args=[obj.pk])
            return format_html(
                '<div style="display:inline-flex; align-items:center; gap:6px; white-space:nowrap;">'
                '<a href="{}" style="display:inline-block; background:#16a34a; color:#fff; padding:4px 9px; '
                'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;">'
                '✅ Finalizar'
                '</a>'
                '<a href="{}" target="_blank" style="display:inline-block; background:#2563eb; color:#fff; padding:4px 9px; '
                'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;" title="Imprimir Venda">'
                '🖨️ Imprimir'
                '</a>'
                '</div>',
                url_fin,
                url_imprimir,
            )
        url_reabrir = reverse('admin:vendas_venda_reabrir', args=[obj.pk])
        return format_html(
            '<div style="display:inline-flex; align-items:center; gap:6px; white-space:nowrap;">'
            '<a href="{}" target="_blank" style="display:inline-block; background:#2563eb; color:#fff; padding:4px 9px; '
            'border-radius:4px; font-weight:700; font-size:11px; line-height:1.3; text-decoration:none;" title="Imprimir Venda">'
            '🖨️ Imprimir'
            '</a>'
            '<a href="{}" onclick="return confirm(\'Reabrir a Venda #{} e estornar seus títulos financeiros?\');" '
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
            return [f.name for f in obj._meta.fields] + ['botao_fechamento_venda']
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        if obj and obj.finalizada and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'vendedor':
            object_id = request.resolver_match.kwargs.get('object_id') if (request and request.resolver_match) else None
            qs = Pessoas.objects.filter(funcionario=True)
            if object_id:
                venda_obj = Venda.objects.filter(pk=object_id).first()
                if venda_obj and venda_obj.vendedor_id:
                    qs = Pessoas.objects.filter(models.Q(funcionario=True) | models.Q(pk=venda_obj.vendedor_id))
            kwargs['queryset'] = qs.order_by('razao_nome')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        venda = form.instance
        venda.calcular_totais()
        venda.save(update_fields=['subtotal', 'valor_total'])

        solicita_finalizar = request.POST.get('_finalizar_venda') == '1'
        if (solicita_finalizar or venda.finalizada) and not venda.titulos_financeiros.exists():
            quitada_param = None
            if '_venda_quitada' in request.POST:
                quitada_param = request.POST.get('_venda_quitada') == '1'
            try:
                titulos = venda.gerar_financeiro(
                    usuario=request.user.username if request.user.is_authenticated else None,
                    quitada=quitada_param,
                )
                situacao_txt = 'QUITADO(S)' if venda.status_financeiro == 'QUITADO' else 'EM ABERTO'
                self.message_user(
                    request,
                    f"Venda #{venda.id:06d} finalizada com sucesso! {len(titulos)} parcela(s) gerada(s) no Contas a Receber ({situacao_txt}).",
                    level=messages.SUCCESS,
                )
            except ValidationError as exc:
                self.message_user(request, '; '.join(exc.messages), level=messages.ERROR)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'preco-produto/<int:produto_id>/',
                self.admin_site.admin_view(self.get_preco_produto),
                name='vendas_venda_preco_produto',
            ),
            path(
                '<int:venda_id>/finalizar/',
                self.admin_site.admin_view(self.finalizar_venda_view),
                name='vendas_venda_finalizar',
            ),
            path(
                '<int:venda_id>/reabrir/',
                self.admin_site.admin_view(self.reabrir_venda_view),
                name='vendas_venda_reabrir',
            ),
            path(
                '<int:venda_id>/imprimir/',
                self.admin_site.admin_view(self.imprimir_venda_view),
                name='vendas_venda_imprimir',
            ),
        ]
        return custom_urls + urls

    def imprimir_venda_view(self, request, venda_id):
        venda = get_object_or_404(
            Venda.objects.select_related('cliente', 'cliente__codigo_cidade', 'vendedor', 'conta_destino'),
            pk=venda_id,
        )
        venda.calcular_totais()
        itens = list(venda.itens.select_related('produto', 'produto__unidade_medida').all())
        titulos = list(venda.titulos)
        empresa = Empresa.get_principal()
        cabecalho = empresa.dados_cabecalho_impressao if empresa else {}

        context = {
            'venda': venda,
            'itens': itens,
            'titulos': titulos,
            'empresa': empresa,
            'cabecalho': cabecalho,
            'vias_range': [1, 2],
        }
        return render(request, 'admin/vendas/venda/imprimir_venda.html', context)

    def get_preco_produto(self, request, produto_id):
        prod = Produtos.objects.filter(pk=produto_id).values('id', 'nome', 'preco_venda').first()
        if not prod:
            return JsonResponse({'preco_venda': '0.00'}, status=404)
        return JsonResponse({
            'id': prod['id'],
            'nome': prod['nome'],
            'preco_venda': str(prod['preco_venda'] or Decimal('0.00')),
        })

    def finalizar_venda_view(self, request, venda_id):
        venda = get_object_or_404(Venda.objects.select_related('cliente', 'vendedor', 'conta_destino'), pk=venda_id)
        if venda.finalizada:
            self.message_user(request, f"A Venda #{venda.id:06d} já se encontra finalizada.", level=messages.WARNING)
            return redirect('admin:vendas_venda_change', venda.pk)

        venda.calcular_totais()
        venda.save(update_fields=['subtotal', 'valor_total'])

        if request.method == 'POST':
            condicao = request.POST.get('condicao_pagamento') or venda.condicao_pagamento or 'DINHEIRO'
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
                desconto_val = venda.desconto or Decimal('0.00')

            quitada = request.POST.get('quitada') == '1'
            numero_nf = (request.POST.get('numero_nf') or '').strip() or None
            numero_cf = (request.POST.get('numero_cupom_fiscal') or '').strip() or None

            try:
                titulos = venda.finalizar_venda(
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
                    f"Venda #{venda.id:06d} finalizada com sucesso! {len(titulos)} título(s) gerado(s) no Contas a Receber como {situacao_txt}.",
                    level=messages.SUCCESS,
                )
                return redirect('admin:vendas_venda_change', venda.pk)
            except ValidationError as exc:
                self.message_user(request, '; '.join(exc.messages), level=messages.ERROR)

        dt_vencimento = venda.data_primeiro_vencimento or timezone.localdate()
        default_quitada = (
            venda.condicao_pagamento in ('DINHEIRO', 'PIX', 'CARTAO_DEBITO')
            and (venda.numero_parcelas or 1) == 1
        )
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Finalizar e Faturar Venda #{venda.id:06d}',
            'venda': venda,
            'condicoes_pagamento': CONDICAO_PAGAMENTO_CHOICES,
            'contas_bancarias': ContaBancaria.objects.filter(ativo=True).order_by('descricao'),
            'data_vencimento_iso': dt_vencimento.isoformat(),
            'default_quitada': default_quitada,
        }
        return render(request, 'admin/vendas/venda/finalizar_venda.html', context)

    def reabrir_venda_view(self, request, venda_id):
        venda = get_object_or_404(Venda, pk=venda_id)
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir vendas finalizadas.", level=messages.ERROR)
            return redirect('admin:vendas_venda_change', venda.pk)

        if venda.finalizada:
            venda.estornar_financeiro(usuario=request.user.username)
            self.message_user(
                request,
                f"Venda #{venda.id:06d} reaberta e títulos do Contas a Receber estornados com sucesso.",
                level=messages.SUCCESS,
            )
        return redirect('admin:vendas_venda_change', venda.pk)

    @admin.action(description="Finalizar e Faturar selecionadas (Gerar Financeiro)")
    def finalizar_e_faturar_vendas(self, request, queryset):
        abertas = queryset.filter(finalizada=False)
        if abertas.count() == 1:
            return redirect('admin:vendas_venda_finalizar', abertas.first().pk)
        count = 0
        for venda in abertas:
            try:
                venda.gerar_financeiro(usuario=request.user.username)
                count += 1
            except ValidationError as exc:
                self.message_user(
                    request,
                    f"Venda #{venda.id:06d}: {'; '.join(exc.messages)}",
                    level=messages.ERROR,
                )
        if count:
            self.message_user(request, f"{count} Venda(s) finalizada(s) e faturada(s) no Financeiro/Estoque com sucesso.")

    @admin.action(description="Reabrir e Estornar Financeiro selecionadas (Desbloquear)")
    def reabrir_e_estornar_vendas(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Apenas administradores podem reabrir vendas finalizadas.", level=messages.ERROR)
            return
        count = 0
        for venda in queryset.filter(finalizada=True):
            venda.estornar_financeiro(usuario=request.user.username)
            count += 1
        self.message_user(request, f"{count} Venda(s) reaberta(s) e financeiro estornado com sucesso.")


@admin.register(ItemVenda)
class ItemVendaAdmin(BaseAdmin):
    list_display = ('id', 'venda', 'sequencia', 'produto', 'quantidade', 'valor_unitario', 'valor_total')
    list_filter = ('venda__status',)
    search_fields = ('venda__id', 'produto__nome', 'produto__codigo_barras')
    autocomplete_fields = ('venda', 'produto')
