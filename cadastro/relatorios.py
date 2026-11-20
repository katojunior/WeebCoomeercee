import csv
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from cadastro.models import Empresa, Pessoas
from financeiro.utils import money


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


def preparar_lote_finalizacao(dados):
    """
    Filtra os registros do relatório que estão aptos para finalização em lote
    (`finalizada=False` e `status != 'CANCELADO'`) e valida a unicidade do cliente.
    """
    elegiveis = []
    ignorados = []
    for r in dados['registros']:
        obj = r['obj']
        if obj.finalizada or obj.status == 'CANCELADO':
            ignorados.append(r)
        else:
            if r['tipo'] == 'VENDA':
                obj.calcular_totais()
            else:
                obj.recalcular_totais(salvar=False)
            r['valor_total'] = obj.valor_total or Decimal('0.00')
            elegiveis.append(r)

    clientes_ids = {r['obj'].cliente_id for r in elegiveis}
    clientes_distintos = len(clientes_ids)
    cliente_lote = None
    sem_cliente = False
    erro_cliente = None

    if not elegiveis:
        erro_cliente = 'Nenhum documento em aberto (não finalizado e não cancelado) foi encontrado para finalizar.'
    elif clientes_distintos > 1:
        erro_cliente = (
            'A finalização em lote exige que todos os documentos selecionados pertençam ao mesmo Cliente. '
            'Filtre por um cliente específico ou desmarque registros de clientes diferentes.'
        )
    else:
        cid = next(iter(clientes_ids))
        if cid is None:
            sem_cliente = True
        else:
            cliente_lote = Pessoas.objects.filter(pk=cid).first()

    total_lote = sum((r['valor_total'] for r in elegiveis), Decimal('0.00'))

    return {
        'elegiveis': elegiveis,
        'ignorados': ignorados,
        'cliente_lote': cliente_lote,
        'sem_cliente': sem_cliente,
        'erro_cliente': erro_cliente,
        'qtd_vendas': sum(1 for r in elegiveis if r['tipo'] == 'VENDA'),
        'qtd_os': sum(1 for r in elegiveis if r['tipo'] == 'OS'),
        'qtd_total': len(elegiveis),
        'total_lote': total_lote,
    }


def _distribuir_desconto_proporcional(elegiveis, desconto_lote):
    """
    Calcula o desconto adicional proporcional a aplicar em cada documento elegível,
    garantindo que a soma exata dos descontos distribuídos feche com `desconto_lote`.
    """
    desc_total = money(desconto_lote or Decimal('0.00'))
    if desc_total <= Decimal('0.00'):
        return {r['chave']: Decimal('0.00') for r in elegiveis}

    positivos = [r for r in elegiveis if r['valor_total'] > Decimal('0.00')]
    base_total = sum((r['valor_total'] for r in positivos), Decimal('0.00'))
    if base_total <= Decimal('0.00'):
        return {r['chave']: Decimal('0.00') for r in elegiveis}

    if desc_total > base_total:
        desc_total = base_total

    alocados = {r['chave']: Decimal('0.00') for r in elegiveis}
    soma_parcial = Decimal('0.00')

    for idx, r in enumerate(positivos):
        if idx == len(positivos) - 1:
            parcela_desc = money(desc_total - soma_parcial)
        else:
            parcela_desc = money((desc_total * r['valor_total']) / base_total)
        parcela_desc = min(parcela_desc, r['valor_total'])
        alocados[r['chave']] = parcela_desc
        soma_parcial += parcela_desc

    # Caso o último tenha sido limitado pelo próprio valor_total, redistribui eventual resíduo
    residuo = money(desc_total - soma_parcial)
    if residuo > Decimal('0.00'):
        for r in positivos:
            margem = r['valor_total'] - alocados[r['chave']]
            if margem > Decimal('0.00'):
                add = min(margem, residuo)
                alocados[r['chave']] += add
                residuo -= add
                if residuo <= Decimal('0.00'):
                    break

    return alocados


def executar_finalizacao_em_lote(
    lote,
    *,
    condicao_pagamento,
    numero_parcelas=1,
    intervalo_dias=30,
    data_primeiro_vencimento=None,
    conta_destino=None,
    desconto_lote=Decimal('0.00'),
    quitada=True,
    usuario=None,
):
    """
    Finaliza em transação atômica todas as Vendas e OS elegíveis do lote,
    aplicando eventual desconto proporcional e gerando os títulos individuais no Contas a Receber.
    """
    if lote['erro_cliente']:
        raise ValidationError(lote['erro_cliente'])

    elegiveis = lote['elegiveis']
    if not elegiveis:
        raise ValidationError('Nenhum documento apto para finalização em lote.')

    if lote['sem_cliente'] and not quitada:
        raise ValidationError(
            'Vendas sem Cliente identificado (Consumidor / Balcão) só podem ser finalizadas em lote como Quitadas.'
        )

    desc_lote = money(desconto_lote or Decimal('0.00'))
    if desc_lote > lote['total_lote']:
        raise ValidationError('O desconto do lote não pode ser maior que o valor total dos documentos.')

    usuario_nome = usuario.username if hasattr(usuario, 'username') else (str(usuario) if usuario else None)
    descontos_extras = _distribuir_desconto_proporcional(elegiveis, desc_lote)
    titulos_criados = []
    chaves_finalizadas = []
    total_finalizado = Decimal('0.00')

    with transaction.atomic():
        for r in elegiveis:
            obj = r['obj']
            extra = descontos_extras.get(r['chave'], Decimal('0.00'))
            novo_desconto = (obj.desconto or Decimal('0.00')) + extra if extra > Decimal('0.00') else None

            if r['tipo'] == 'VENDA':
                titulos = obj.finalizar_venda(
                    condicao_pagamento=condicao_pagamento,
                    numero_parcelas=numero_parcelas,
                    intervalo_dias=intervalo_dias,
                    data_primeiro_vencimento=data_primeiro_vencimento,
                    conta_destino=conta_destino,
                    desconto=novo_desconto,
                    quitada=quitada,
                    usuario=usuario_nome,
                )
            else:
                titulos = obj.finalizar_os(
                    condicao_pagamento=condicao_pagamento,
                    numero_parcelas=numero_parcelas,
                    intervalo_dias=intervalo_dias,
                    data_primeiro_vencimento=data_primeiro_vencimento,
                    conta_destino=conta_destino,
                    desconto=novo_desconto,
                    quitada=quitada,
                    usuario=usuario_nome,
                )

            titulos_criados.extend(titulos)
            chaves_finalizadas.append(r['chave'])
            total_finalizado += obj.valor_total or Decimal('0.00')

    return {
        'chaves_finalizadas': chaves_finalizadas,
        'qtd_vendas': lote['qtd_vendas'],
        'qtd_os': lote['qtd_os'],
        'qtd_docs': len(chaves_finalizadas),
        'qtd_titulos': len(titulos_criados),
        'titulos': titulos_criados,
        'desconto_aplicado': desc_lote,
        'total_finalizado': total_finalizado,
        'quitada': quitada,
    }
