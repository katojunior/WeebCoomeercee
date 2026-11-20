from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from unidecode import unidecode

from cadastro.models import Empresa
from cadastro_produto.models import NumeroSerie, Produtos
from .models import MovimentacaoEstoque


TIPOS_ENTRADA = {'ENTRADA', 'AJUSTE_ENTRADA'}
TIPOS_SAIDA = {'SAIDA', 'AJUSTE_SAIDA'}
TIPOS_AJUSTE = {'AJUSTE_ENTRADA', 'AJUSTE_SAIDA'}
QTD_ZERO = Decimal('0.000')


def normalizar_lista_novos_seriais(novos_seriais):
    """Normaliza e remove vazios de uma lista de novos números de série."""
    if not novos_seriais:
        return []
    return [unidecode(str(item)).upper().strip() for item in novos_seriais if str(item).strip()]


def _to_decimal_qtd(valor):
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal('0.001'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def empresa_bloqueia_sem_estoque():
    """Indica se a empresa matriz está configurada para bloquear fechamento sem saldo."""
    empresa = Empresa.objects.filter(matriz=True).first() or Empresa.objects.first()
    return bool(empresa.bloquear_fechamento_sem_estoque) if empresa else False


def _validar_regras_gerais(mov, erros):
    qtd = _to_decimal_qtd(mov.quantidade)
    if qtd is None or qtd <= QTD_ZERO:
        erros['quantidade'] = 'A quantidade deve ser maior que zero.'
    else:
        mov.quantidade = qtd

    if mov.tipo not in (TIPOS_ENTRADA | TIPOS_SAIDA):
        erros['tipo'] = 'Tipo de movimentação inválido.'

    if mov.tipo in TIPOS_AJUSTE and not (mov.motivo and mov.motivo.strip()):
        erros['motivo'] = 'Informe o motivo/justificativa para ajustes de inventário.'


def _validar_seriais(mov, seriais, novos_seriais, erros):
    produto = mov.produto if mov.produto_id else None
    seriais = list(seriais or [])
    novos_normalizados = normalizar_lista_novos_seriais(novos_seriais)

    if not produto:
        return

    if not produto.controla_numero_serie:
        if seriais or novos_normalizados:
            erros['numeros_serie'] = 'Este produto não controla números de série.'
        return

    if novos_normalizados and mov.tipo not in TIPOS_ENTRADA:
        erros['numeros_serie_novos'] = 'Novos números de série só podem ser informados em entradas.'
        return

    if len(set(novos_normalizados)) != len(novos_normalizados):
        erros['numeros_serie_novos'] = 'Há números de série repetidos na lista informada.'
        return

    if novos_normalizados:
        existentes = list(
            NumeroSerie.objects.filter(numero_serie__in=novos_normalizados)
            .values_list('numero_serie', flat=True)
        )
        if existentes:
            erros['numeros_serie_novos'] = (
                f'Números de série já cadastrados no sistema: {", ".join(existentes)}.'
            )
            return

    serial_ids = [s.pk for s in seriais]
    if len(set(serial_ids)) != len(serial_ids):
        erros['numeros_serie'] = 'Há números de série duplicados selecionados.'
        return

    qtd = _to_decimal_qtd(mov.quantidade)
    if qtd is None or qtd <= QTD_ZERO:
        return

    if qtd != qtd.to_integral_value():
        erros['quantidade'] = (
            'Produtos que controlam número de série exigem quantidade inteira exata.'
        )
        return

    qtd_int = int(qtd)
    total_seriais = len(seriais) + len(novos_normalizados)
    if total_seriais != qtd_int:
        erros['numeros_serie'] = (
            f'Produto "{produto.nome}" controla número de série: informe exatamente '
            f'{qtd_int} serial(is) (recebido: {total_seriais}).'
        )
        return

    for serial in seriais:
        if serial.produto_id != produto.pk:
            erros['numeros_serie'] = f'O serial {serial.numero_serie} não pertence ao produto selecionado.'
            return
        if mov.tipo in TIPOS_ENTRADA:
            if serial.status == 'DISPONIVEL':
                erros['numeros_serie'] = f'O serial {serial.numero_serie} já está disponível em estoque.'
                return
        else:
            if serial.status != 'DISPONIVEL':
                erros['numeros_serie'] = (
                    f'O serial {serial.numero_serie} não está disponível em estoque '
                    f'(status atual: {serial.get_status_display()}).'
                )
                return


def validar_movimentacao(
    mov,
    seriais=None,
    novos_seriais=None,
    verificar_saldo=True,
    permitir_saldo_negativo=False,
):
    """Valida regras estruturais, saldo único e números de série de uma movimentação."""
    erros = {}
    _validar_regras_gerais(mov, erros)
    _validar_seriais(mov, seriais, novos_seriais, erros)

    if (
        verificar_saldo
        and not permitir_saldo_negativo
        and not erros
        and mov.produto_id
        and mov.tipo in TIPOS_SAIDA
        and not mov.produto.controla_numero_serie
    ):
        saldo_atual = mov.produto.estoque_atual or QTD_ZERO
        if saldo_atual < mov.quantidade:
            erros['quantidade'] = (
                f'Saldo insuficiente para "{mov.produto.nome}": '
                f'disponível {saldo_atual}, solicitado {mov.quantidade}.'
            )

    if erros:
        raise ValidationError(erros)


def _processar_seriais_movimentacao(mov, seriais, novos_normalizados):
    seriais_finais = []

    if mov.tipo in TIPOS_ENTRADA:
        fornecedor = (
            mov.pessoa
            if mov.tipo == 'ENTRADA' and mov.origem != 'ESTORNO' and mov.pessoa and mov.pessoa.tipo_pessoa in (1, 2)
            else None
        )
        for codigo in novos_normalizados:
            serial = NumeroSerie(
                produto=mov.produto,
                numero_serie=codigo,
                status='DISPONIVEL',
                fornecedor=fornecedor,
                nota_fiscal_entrada=mov.documento_referencia if mov.tipo == 'ENTRADA' else None,
            )
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

        for serial in seriais:
            serial.status = 'DISPONIVEL'
            if mov.origem == 'ESTORNO':
                serial.cliente = None
                serial.nota_fiscal_saida = None
                serial.data_venda = None
                serial.data_fim_garantia = None
            else:
                if fornecedor and not serial.fornecedor_id:
                    serial.fornecedor = fornecedor
                if mov.tipo == 'ENTRADA' and mov.documento_referencia and not serial.nota_fiscal_entrada:
                    serial.nota_fiscal_entrada = mov.documento_referencia
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

    elif mov.tipo in TIPOS_SAIDA:
        agora = timezone.now()
        for serial in seriais:
            if mov.tipo == 'SAIDA':
                serial.status = 'VENDIDO'
                if mov.pessoa and mov.pessoa.tipo_pessoa in (0, 2):
                    serial.cliente = mov.pessoa
                if mov.documento_referencia:
                    serial.nota_fiscal_saida = mov.documento_referencia
                if not serial.data_venda:
                    serial.data_venda = agora
                if not serial.data_fim_garantia:
                    serial.data_fim_garantia = serial.calcular_data_fim_garantia()
            else:
                serial.status = 'BAIXADO'
                if mov.motivo:
                    registro_rma = f'[AJUSTE SAIDA] {mov.motivo}'
                    serial.historico_rma = (
                        f'{serial.historico_rma}\n{registro_rma}'.strip()
                        if serial.historico_rma
                        else registro_rma
                    )
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

    return seriais_finais


@transaction.atomic
def aplicar_movimentacao(
    mov,
    seriais=None,
    novos_seriais=None,
    permitir_saldo_negativo=False,
):
    """Aplica movimentação com lock transacional no produto e grava snapshots de saldo."""
    produto = Produtos.objects.select_for_update().get(pk=mov.produto_id)
    mov.produto = produto

    seriais = list(seriais or [])
    novos_normalizados = normalizar_lista_novos_seriais(novos_seriais)
    validar_movimentacao(
        mov,
        seriais=seriais,
        novos_seriais=novos_normalizados,
        verificar_saldo=True,
        permitir_saldo_negativo=permitir_saldo_negativo,
    )

    saldo_anterior = _to_decimal_qtd(produto.estoque_atual) or QTD_ZERO
    mov.saldo_anterior_produto = saldo_anterior

    seriais_finais = (
        _processar_seriais_movimentacao(mov, seriais, novos_normalizados)
        if produto.controla_numero_serie
        else []
    )

    if produto.controla_numero_serie:
        qtd_disp = produto.numeros_serie.filter(status='DISPONIVEL').count()
        novo_total = Decimal(qtd_disp).quantize(Decimal('0.001'))
    else:
        delta = mov.quantidade if mov.tipo in TIPOS_ENTRADA else -mov.quantidade
        novo_total = (saldo_anterior + delta).quantize(Decimal('0.001'))

    produto.estoque_atual = novo_total
    produto.save(update_fields=['estoque_atual'])

    mov.saldo_posterior_produto = novo_total
    mov._aplicado_via_servico = True
    mov._validado_via_servico = True
    return seriais_finais


@transaction.atomic
def registrar_movimentacao(
    *,
    produto,
    tipo,
    quantidade,
    origem='MANUAL',
    venda=None,
    ordem_servico=None,
    numeros_serie=None,
    numeros_serie_novos=None,
    pessoa=None,
    documento_referencia=None,
    motivo=None,
    observacoes=None,
    permitir_saldo_negativo=False,
    usuario=None,
):
    """Cria e aplica atomicamente uma movimentação do estoque único."""
    mov = MovimentacaoEstoque(
        produto=produto,
        tipo=tipo,
        origem=origem,
        quantidade=quantidade,
        venda=venda,
        ordem_servico=ordem_servico,
        pessoa=pessoa,
        documento_referencia=documento_referencia,
        motivo=motivo,
        observacoes=observacoes,
        usuario=usuario,
    )
    seriais_finais = aplicar_movimentacao(
        mov,
        seriais=numeros_serie,
        novos_seriais=numeros_serie_novos,
        permitir_saldo_negativo=permitir_saldo_negativo,
    )
    mov.save()
    if seriais_finais:
        mov.numeros_serie.set(seriais_finais)
    return mov


@transaction.atomic
def baixar_estoque_itens(
    *,
    origem,
    itens,
    pessoa=None,
    documento_referencia=None,
    venda=None,
    ordem_servico=None,
    usuario=None,
):
    """
    Executa a baixa automática de saída dos itens elegíveis de uma Venda ou OS.
    Garante idempotência via `item.movimentacao_saida`.
    """
    permitir_negativo = not empresa_bloqueia_sem_estoque()
    movs_criadas = []

    for item in itens:
        if getattr(item, 'movimentacao_saida_id', None):
            continue
        if not getattr(item, 'produto_id', None):
            continue
        if getattr(item, 'tipo_item', 'PECA') != 'PECA':
            continue

        produto = item.produto
        if not produto.controla_estoque:
            continue

        qtd = _to_decimal_qtd(item.quantidade)
        if qtd is None or qtd <= QTD_ZERO:
            continue

        seriais = list(item.numeros_serie.all())
        mov = registrar_movimentacao(
            produto=produto,
            tipo='SAIDA',
            origem=origem,
            quantidade=qtd,
            venda=venda,
            ordem_servico=ordem_servico,
            numeros_serie=seriais,
            pessoa=pessoa,
            documento_referencia=documento_referencia,
            motivo=f'Baixa automática ({origem}) {documento_referencia or ""}'.strip(),
            permitir_saldo_negativo=permitir_negativo,
            usuario=usuario,
        )
        item.movimentacao_saida = mov
        item.save(update_fields=['movimentacao_saida'])
        movs_criadas.append(mov)

    return movs_criadas


@transaction.atomic
def estornar_estoque_itens(
    *,
    itens,
    motivo_estorno,
    pessoa=None,
    documento_referencia=None,
    venda=None,
    ordem_servico=None,
    usuario=None,
):
    """
    Gera movimentações inversas de ENTRADA (origem='ESTORNO') ao reabrir Venda/OS,
    devolvendo o saldo e restaurando eventuais números de série para DISPONIVEL.
    """
    movs_estorno = []

    for item in itens:
        if not getattr(item, 'movimentacao_saida_id', None):
            continue

        mov_saida = item.movimentacao_saida
        seriais = list(mov_saida.numeros_serie.all())

        mov_inv = registrar_movimentacao(
            produto=mov_saida.produto,
            tipo='ENTRADA',
            origem='ESTORNO',
            quantidade=mov_saida.quantidade,
            venda=venda,
            ordem_servico=ordem_servico,
            numeros_serie=seriais,
            pessoa=pessoa,
            documento_referencia=documento_referencia,
            motivo=motivo_estorno,
            observacoes=f'Estorno da movimentação de saída #{mov_saida.id}',
            permitir_saldo_negativo=True,
            usuario=usuario,
        )
        item.movimentacao_saida = None
        item.save(update_fields=['movimentacao_saida'])
        movs_estorno.append(mov_inv)

    return movs_estorno
