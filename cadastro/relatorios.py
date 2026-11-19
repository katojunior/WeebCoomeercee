import csv
import datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from cadastro.models import Empresa, Pessoas


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, datetime.date):
        return val
    try:
        return datetime.date.fromisoformat(str(val).strip())
    except ValueError:
        return None


def _aware_datetime(d, is_end=False):
    if is_end:
        d = d + datetime.timedelta(days=1)
    dt = datetime.datetime.combine(d, datetime.time.min)
    if settings.USE_TZ and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _calcular_em_aberto(obj, titulos):
    """
    Calcula o valor em aberto do documento:
    - Se não finalizada (`finalizada=False`): todo o `valor_total` está pendente de fechamento.
    - Se já finalizada (`finalizada=True`): soma o `saldo_devedor` dos títulos financeiros ainda em aberto/parciais.
    """
    if not obj.finalizada:
        return obj.valor_total or Decimal('0.00')
    if titulos:
        return sum(
            (t.saldo_devedor or Decimal('0.00') for t in titulos if t.status in ('ABERTO', 'PARCIAL')),
            Decimal('0.00'),
        )
    return Decimal('0.00')


ORDENACAO_CAMPOS = {
    'data': 'Data',
    'id': 'Número / Documento',
    'tipo': 'Tipo (Venda / OS)',
    'cliente': 'Cliente',
    'status': 'Status',
    'valor_total': 'Valor Total',
    'valor_em_aberto': 'Valor em Aberto',
}


def _ordenar_registros(registros, ordenar_por='data', direcao='desc'):
    campo = ordenar_por if ordenar_por in ORDENACAO_CAMPOS else 'data'
    is_desc = direcao != 'asc'

    def _ts(r):
        return r['data'].timestamp() if r['data'] else 0

    key_funcs = {
        'data': lambda r: (_ts(r), r['tipo'], r['id']),
        'id': lambda r: (r['id'], r['tipo']),
        'tipo': lambda r: (r['tipo'], _ts(r), r['id']),
        'cliente': lambda r: ((r['cliente_nome'] or '').upper(), _ts(r), r['id']),
        'status': lambda r: ((r['status_display'] or '').upper(), _ts(r), r['id']),
        'valor_total': lambda r: (r['valor_total'], _ts(r), r['id']),
        'valor_em_aberto': lambda r: (r['valor_em_aberto'], _ts(r), r['id']),
    }
    registros.sort(key=key_funcs[campo], reverse=is_desc)


def consultar_resumo_cliente(
    *,
    cliente_id=None,
    data_inicio=None,
    data_fim=None,
    situacao='abertos',
    tipo_doc='ambos',
    ocultar_cancelados=True,
    ordenar_por='data',
    direcao='desc',
    selected_keys=None,
    limite_sem_cliente=250,
):
    """
    Consulta consolidada de Vendas e Ordens de Serviço por cliente, período e situação,
    calculando os totalizadores gerais e em aberto para exibição, exportação CSV ou impressão em lote.
    """
    from ordem_servico.models import OrdemServico
    from vendas.models import Venda

    dt_ini = _parse_date(data_inicio)
    dt_fim = _parse_date(data_fim)
    if dt_ini and dt_fim and dt_ini > dt_fim:
        dt_ini, dt_fim = dt_fim, dt_ini

    cliente = None
    if cliente_id:
        cliente = (
            Pessoas.objects.select_related('codigo_cidade', 'codigo_cidade__uf')
            .filter(pk=cliente_id)
            .first()
        )

    selected_set = set(selected_keys) if selected_keys else None
    ordenar_por = ordenar_por if ordenar_por in ORDENACAO_CAMPOS else 'data'
    direcao = 'asc' if direcao == 'asc' else 'desc'
    prefix = '' if direcao == 'asc' else '-'

    registros = []

    # --- 1. VENDAS ---
    if tipo_doc in ('ambos', 'vendas'):
        qs_vendas = Venda.objects.select_related(
            'cliente',
            'cliente__codigo_cidade',
            'cliente__codigo_cidade__uf',
            'vendedor',
            'conta_destino',
        ).prefetch_related(
            'itens',
            'itens__produto',
            'itens__produto__unidade_medida',
            'titulos_financeiros',
        )

        if cliente_id:
            qs_vendas = qs_vendas.filter(cliente_id=cliente_id)
        if ocultar_cancelados:
            qs_vendas = qs_vendas.exclude(status='CANCELADO')
        if dt_ini:
            qs_vendas = qs_vendas.filter(data_venda__gte=_aware_datetime(dt_ini, is_end=False))
        if dt_fim:
            qs_vendas = qs_vendas.filter(data_venda__lt=_aware_datetime(dt_fim, is_end=True))

        if situacao == 'abertos':
            qs_vendas = qs_vendas.filter(finalizada=False)
        elif situacao == 'abertos_ou_financeiro':
            qs_vendas = qs_vendas.filter(
                Q(finalizada=False) | Q(titulos_financeiros__status__in=['ABERTO', 'PARCIAL'])
            ).distinct()
        elif situacao == 'finalizados':
            qs_vendas = qs_vendas.filter(finalizada=True)

        venda_order_map = {
            'data': (f'{prefix}data_venda', f'{prefix}id'),
            'id': (f'{prefix}id',),
            'cliente': (f'{prefix}cliente__razao_nome', f'{prefix}data_venda'),
            'status': (f'{prefix}status', f'{prefix}data_venda'),
            'valor_total': (f'{prefix}valor_total', f'{prefix}data_venda'),
        }
        qs_vendas = qs_vendas.order_by(*venda_order_map.get(ordenar_por, (f'{prefix}data_venda', f'{prefix}id')))
        if not cliente_id and not selected_set:
            qs_vendas = qs_vendas[:limite_sem_cliente]

        for v in qs_vendas:
            chave = f'V-{v.id}'
            if selected_set is not None and chave not in selected_set:
                continue
            itens = list(v.itens.all())
            titulos = sorted(v.titulos_financeiros.all(), key=lambda t: (t.data_vencimento, t.id))
            em_aberto = _calcular_em_aberto(v, titulos)
            if situacao == 'abertos_ou_financeiro' and v.finalizada and em_aberto <= Decimal('0.00'):
                continue

            resumo_itens = ', '.join(
                f"{it.quantidade:g}x {it.produto.nome}" for it in itens[:3] if it.produto_id
            )
            if len(itens) > 3:
                resumo_itens += f' (+{len(itens) - 3})'

            registros.append({
                'chave': chave,
                'tipo': 'VENDA',
                'tipo_label': 'Venda',
                'id': v.id,
                'numero': f'VND #{v.id:06d}',
                'data': v.data_venda or v.data_hora,
                'cliente_nome': v.cliente.razao_nome if v.cliente else 'CONSUMIDOR / BALCÃO',
                'responsavel': v.vendedor.razao_nome if v.vendedor else '—',
                'resumo': resumo_itens or 'Venda de Mercadorias',
                'status_display': v.get_status_display(),
                'finalizada': v.finalizada,
                'status_financeiro': v.status_financeiro,
                'condicao_pagamento': v.get_condicao_pagamento_display(),
                'valor_total': v.valor_total or Decimal('0.00'),
                'valor_em_aberto': em_aberto,
                'url_admin': reverse('admin:vendas_venda_change', args=[v.id]),
                'url_imprimir': reverse('admin:vendas_venda_imprimir', args=[v.id]),
                'obj': v,
                'itens': itens,
                'titulos': titulos,
            })

    # --- 2. ORDENS DE SERVIÇO ---
    if tipo_doc in ('ambos', 'ordens'):
        qs_os = OrdemServico.objects.select_related(
            'cliente',
            'cliente__codigo_cidade',
            'cliente__codigo_cidade__uf',
            'equipamento',
            'equipamento__marca',
            'tecnico',
            'conta_destino',
        ).prefetch_related(
            'itens',
            'itens__produto',
            'itens__equipamento',
            'titulos_financeiros',
        )

        if cliente_id:
            qs_os = qs_os.filter(cliente_id=cliente_id)
        if ocultar_cancelados:
            qs_os = qs_os.exclude(status='CANCELADO')
        if dt_ini:
            qs_os = qs_os.filter(data_abertura__gte=_aware_datetime(dt_ini, is_end=False))
        if dt_fim:
            qs_os = qs_os.filter(data_abertura__lt=_aware_datetime(dt_fim, is_end=True))

        if situacao == 'abertos':
            qs_os = qs_os.filter(finalizada=False)
        elif situacao == 'abertos_ou_financeiro':
            qs_os = qs_os.filter(
                Q(finalizada=False) | Q(titulos_financeiros__status__in=['ABERTO', 'PARCIAL'])
            ).distinct()
        elif situacao == 'finalizados':
            qs_os = qs_os.filter(finalizada=True)

        os_order_map = {
            'data': (f'{prefix}data_abertura', f'{prefix}id'),
            'id': (f'{prefix}id',),
            'cliente': (f'{prefix}cliente__razao_nome', f'{prefix}data_abertura'),
            'status': (f'{prefix}status', f'{prefix}data_abertura'),
            'valor_total': (f'{prefix}valor_total', f'{prefix}data_abertura'),
        }
        qs_os = qs_os.order_by(*os_order_map.get(ordenar_por, (f'{prefix}data_abertura', f'{prefix}id')))
        if not cliente_id and not selected_set:
            qs_os = qs_os[:limite_sem_cliente]

        for os_obj in qs_os:
            chave = f'OS-{os_obj.id}'
            if selected_set is not None and chave not in selected_set:
                continue
            itens = list(os_obj.itens.all())
            titulos = sorted(os_obj.titulos_financeiros.all(), key=lambda t: (t.data_vencimento, t.id))
            em_aberto = _calcular_em_aberto(os_obj, titulos)
            if situacao == 'abertos_ou_financeiro' and os_obj.finalizada and em_aberto <= Decimal('0.00'):
                continue

            equip_txt = str(os_obj.equipamento) if os_obj.equipamento else ''
            defeito_txt = (os_obj.defeito_reclamado or '')[:60]
            resumo_os = ' — '.join(p for p in (equip_txt, defeito_txt) if p) or 'Ordem de Serviço'

            registros.append({
                'chave': chave,
                'tipo': 'OS',
                'tipo_label': 'Ordem de Serviço',
                'id': os_obj.id,
                'numero': f'OS #{os_obj.id:06d}',
                'data': os_obj.data_abertura or os_obj.data_hora,
                'cliente_nome': os_obj.cliente.razao_nome if os_obj.cliente else '—',
                'responsavel': os_obj.tecnico.razao_nome if os_obj.tecnico else '—',
                'resumo': resumo_os,
                'status_display': os_obj.get_status_display(),
                'finalizada': os_obj.finalizada,
                'status_financeiro': os_obj.status_financeiro,
                'condicao_pagamento': os_obj.get_condicao_pagamento_display(),
                'valor_total': os_obj.valor_total or Decimal('0.00'),
                'valor_em_aberto': em_aberto,
                'url_admin': reverse('admin:ordem_servico_ordemservico_change', args=[os_obj.id]),
                'url_imprimir': reverse('admin:ordem_servico_ordemservico_imprimir', args=[os_obj.id]),
                'obj': os_obj,
                'itens': itens,
                'titulos': titulos,
            })

    # Ordenação unificada configurável (crescente/decrescente)
    _ordenar_registros(registros, ordenar_por=ordenar_por, direcao=direcao)

    vendas_regs = [r for r in registros if r['tipo'] == 'VENDA']
    os_regs = [r for r in registros if r['tipo'] == 'OS']

    total_vendas = sum((r['valor_total'] for r in vendas_regs), Decimal('0.00'))
    total_os = sum((r['valor_total'] for r in os_regs), Decimal('0.00'))
    total_geral = total_vendas + total_os

    em_aberto_vendas = sum((r['valor_em_aberto'] for r in vendas_regs), Decimal('0.00'))
    em_aberto_os = sum((r['valor_em_aberto'] for r in os_regs), Decimal('0.00'))
    em_aberto_geral = em_aberto_vendas + em_aberto_os

    empresa = Empresa.get_principal()

    return {
        'cliente': cliente,
        'empresa': empresa,
        'cabecalho': empresa.dados_cabecalho_impressao if empresa else {},
        'data_inicio': dt_ini,
        'data_fim': dt_fim,
        'situacao': situacao,
        'tipo_doc': tipo_doc,
        'ocultar_cancelados': ocultar_cancelados,
        'ordenar_por': ordenar_por,
        'ordenar_por_label': ORDENACAO_CAMPOS[ordenar_por],
        'direcao': direcao,
        'direcao_label': 'Crescente' if direcao == 'asc' else 'Decrescente',
        'registros': registros,
        'qtd_vendas': len(vendas_regs),
        'qtd_os': len(os_regs),
        'qtd_total': len(registros),
        'total_vendas': total_vendas,
        'total_os': total_os,
        'total_geral': total_geral,
        'em_aberto_vendas': em_aberto_vendas,
        'em_aberto_os': em_aberto_os,
        'em_aberto_geral': em_aberto_geral,
    }


def exportar_resumo_csv(dados):
    """Gera resposta HTTP com CSV (UTF-8 BOM, separador ';') para abertura direta no Excel."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    nome_cli = f"_{dados['cliente'].id}" if dados['cliente'] else ''
    response['Content-Disposition'] = f'attachment; filename="resumo_vendas_os{nome_cli}.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Tipo',
        'Número',
        'Data',
        'Cliente',
        'Vendedor / Técnico',
        'Resumo / Equipamento / Itens',
        'Status',
        'Finalizada',
        'Financeiro',
        'Condição de Pagamento',
        'Valor Total (R$)',
        'Valor em Aberto (R$)',
    ])

    for r in dados['registros']:
        dt_str = timezone.localtime(r['data']).strftime('%d/%m/%Y %H:%M') if r['data'] else ''
        writer.writerow([
            r['tipo_label'],
            r['numero'],
            dt_str,
            r['cliente_nome'],
            r['responsavel'],
            r['resumo'],
            r['status_display'],
            'SIM' if r['finalizada'] else 'NÃO',
            r['status_financeiro'],
            r['condicao_pagamento'],
            f"{r['valor_total']:.2f}".replace('.', ','),
            f"{r['valor_em_aberto']:.2f}".replace('.', ','),
        ])

    writer.writerow([])
    writer.writerow(['TOTAIS', '', '', '', '', '', '', '', '', 'Vendas:', f"{dados['total_vendas']:.2f}".replace('.', ','), f"{dados['em_aberto_vendas']:.2f}".replace('.', ',')])
    writer.writerow(['TOTAIS', '', '', '', '', '', '', '', '', 'Ordens de Serviço:', f"{dados['total_os']:.2f}".replace('.', ','), f"{dados['em_aberto_os']:.2f}".replace('.', ',')])
    writer.writerow(['TOTAIS', '', '', '', '', '', '', '', '', 'TOTAL GERAL:', f"{dados['total_geral']:.2f}".replace('.', ','), f"{dados['em_aberto_geral']:.2f}".replace('.', ',')])
    return response
