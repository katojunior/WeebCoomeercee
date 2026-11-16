from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from unidecode import unidecode

from cadastro_produto.models import NumeroSerie, Produtos
from .models import EstoqueLocalizacao, MovimentacaoEstoque


TIPOS_ENTRADA = {'ENTRADA', 'AJUSTE_ENTRADA'}
TIPOS_SAIDA = {'SAIDA', 'AJUSTE_SAIDA'}
TIPOS_AJUSTE = {'AJUSTE_ENTRADA', 'AJUSTE_SAIDA'}


def normalizar_lista_novos_seriais(novos_seriais):
    """Normaliza e remove vazios de uma lista de novos números de série."""
    if not novos_seriais:
        return []
    return [unidecode(str(item)).upper().strip() for item in novos_seriais if str(item).strip()]


def _obter_saldo_localizacao(produto, localizacao, lock=False):
    if not produto or not localizacao:
        return None, 0
    qs = EstoqueLocalizacao.objects
    if lock:
        qs = qs.select_for_update()
    saldo_obj = qs.filter(produto=produto, localizacao=localizacao).first()
    return saldo_obj, (saldo_obj.quantidade if saldo_obj else 0)


def _validar_regras_localizacao_e_motivo(mov, erros):
    if not mov.quantidade or mov.quantidade <= 0:
        erros['quantidade'] = 'A quantidade deve ser maior que zero.'

    if mov.tipo in TIPOS_AJUSTE and not (mov.motivo and mov.motivo.strip()):
        erros['motivo'] = 'Informe o motivo/justificativa para ajustes de inventário.'

    if mov.tipo in TIPOS_ENTRADA:
        if not mov.localizacao_destino_id:
            erros['localizacao_destino'] = 'Informe a localização de destino para entradas.'
        elif not mov.localizacao_destino.ativo:
            erros['localizacao_destino'] = 'A localização de destino está inativa.'
        if mov.localizacao_origem_id:
            erros['localizacao_origem'] = 'Entradas não devem possuir localização de origem.'
    elif mov.tipo in TIPOS_SAIDA:
        if not mov.localizacao_origem_id:
            erros['localizacao_origem'] = 'Informe a localização de origem para saídas.'
        if mov.localizacao_destino_id:
            erros['localizacao_destino'] = 'Saídas não devem possuir localização de destino.'
    elif mov.tipo == 'TRANSFERENCIA':
        if not mov.localizacao_origem_id:
            erros['localizacao_origem'] = 'Informe a localização de origem da transferência.'
        if not mov.localizacao_destino_id:
            erros['localizacao_destino'] = 'Informe a localização de destino da transferência.'
        elif not mov.localizacao_destino.ativo:
            erros['localizacao_destino'] = 'A localização de destino está inativa.'
        if (
            mov.localizacao_origem_id
            and mov.localizacao_destino_id
            and mov.localizacao_origem_id == mov.localizacao_destino_id
        ):
            erros['localizacao_destino'] = 'A localização de destino deve ser diferente da origem.'
    else:
        erros['tipo'] = 'Tipo de movimentação inválido.'


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

    total_seriais = len(seriais) + len(novos_normalizados)
    if not mov.quantidade or total_seriais != mov.quantidade:
        erros['numeros_serie'] = (
            f'Produto controla número de série: informe exatamente {mov.quantidade or 0} serial(is) '
            f'(recebido: {total_seriais}).'
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
            if (
                mov.localizacao_origem_id
                and serial.localizacao_estoque_id != mov.localizacao_origem_id
            ):
                erros['numeros_serie'] = (
                    f'O serial {serial.numero_serie} não está alocado na localização de origem informada.'
                )
                return


def validar_movimentacao(mov, seriais=None, novos_seriais=None, verificar_saldo=True):
    """Valida regras estruturais, saldo em origem e números de série de uma movimentação."""
    erros = {}
    _validar_regras_localizacao_e_motivo(mov, erros)
    _validar_seriais(mov, seriais, novos_seriais, erros)

    if (
        verificar_saldo
        and not erros
        and mov.produto_id
        and mov.localizacao_origem_id
        and mov.tipo in (TIPOS_SAIDA | {'TRANSFERENCIA'})
    ):
        _, saldo_origem = _obter_saldo_localizacao(mov.produto, mov.localizacao_origem, lock=False)
        if saldo_origem < mov.quantidade:
            erros['quantidade'] = (
                f'Saldo insuficiente na localização {mov.localizacao_origem.codigo}: '
                f'disponível {saldo_origem}, solicitado {mov.quantidade}.'
            )

    if erros:
        raise ValidationError(erros)


def _atualizar_saldo_localizacao(produto, localizacao, delta):
    saldo_obj, saldo_anterior = _obter_saldo_localizacao(produto, localizacao, lock=True)
    saldo_posterior = saldo_anterior + delta
    if saldo_posterior < 0:
        raise ValidationError({
            'quantidade': (
                f'Saldo insuficiente na localização {localizacao.codigo}: '
                f'disponível {saldo_anterior}, alteração solicitada {delta}.'
            )
        })
    if saldo_obj is None:
        saldo_obj = EstoqueLocalizacao.objects.create(
            produto=produto,
            localizacao=localizacao,
            quantidade=saldo_posterior,
        )
    else:
        saldo_obj.quantidade = saldo_posterior
        saldo_obj.save(update_fields=['quantidade', 'data_hora_atualizada'])
    return saldo_anterior, saldo_posterior


def _processar_seriais_movimentacao(mov, seriais, novos_normalizados):
    seriais_finais = []

    if mov.tipo in TIPOS_ENTRADA:
        for codigo in novos_normalizados:
            fornecedor = (
                mov.pessoa
                if mov.tipo == 'ENTRADA' and mov.pessoa and mov.pessoa.tipo_pessoa in (1, 2)
                else None
            )
            serial = NumeroSerie(
                produto=mov.produto,
                numero_serie=codigo,
                status='DISPONIVEL',
                localizacao_estoque=mov.localizacao_destino,
                fornecedor=fornecedor,
                nota_fiscal_entrada=mov.documento_referencia if mov.tipo == 'ENTRADA' else None,
            )
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

        for serial in seriais:
            serial.status = 'DISPONIVEL'
            serial.localizacao_estoque = mov.localizacao_destino
            if mov.tipo == 'ENTRADA' and mov.pessoa and mov.pessoa.tipo_pessoa in (1, 2) and not serial.fornecedor_id:
                serial.fornecedor = mov.pessoa
            if mov.tipo == 'ENTRADA' and mov.documento_referencia and not serial.nota_fiscal_entrada:
                serial.nota_fiscal_entrada = mov.documento_referencia
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

    elif mov.tipo == 'TRANSFERENCIA':
        for serial in seriais:
            serial.localizacao_estoque = mov.localizacao_destino
            serial._skip_sync_estoque = True
            serial.save()
            seriais_finais.append(serial)

    elif mov.tipo in TIPOS_SAIDA:
        agora = timezone.now()
        for serial in seriais:
            serial.localizacao_estoque = None
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
def aplicar_movimentacao(mov, seriais=None, novos_seriais=None):
    """Aplica validando com lock transacional e preenche os snapshots na movimentação."""
    produto = Produtos.objects.select_for_update().get(pk=mov.produto_id)
    mov.produto = produto

    seriais = list(seriais or [])
    novos_normalizados = normalizar_lista_novos_seriais(novos_seriais)
    validar_movimentacao(mov, seriais=seriais, novos_seriais=novos_normalizados, verificar_saldo=False)

    mov.saldo_anterior_produto = produto.estoque_atual

    if mov.tipo in TIPOS_ENTRADA:
        ant_dest, pos_dest = _atualizar_saldo_localizacao(produto, mov.localizacao_destino, mov.quantidade)
        mov.saldo_anterior_destino = ant_dest
        mov.saldo_posterior_destino = pos_dest
        mov.saldo_anterior_origem = None
        mov.saldo_posterior_origem = None
    elif mov.tipo in TIPOS_SAIDA:
        ant_orig, pos_orig = _atualizar_saldo_localizacao(produto, mov.localizacao_origem, -mov.quantidade)
        mov.saldo_anterior_origem = ant_orig
        mov.saldo_posterior_origem = pos_orig
        mov.saldo_anterior_destino = None
        mov.saldo_posterior_destino = None
    elif mov.tipo == 'TRANSFERENCIA':
        ant_orig, pos_orig = _atualizar_saldo_localizacao(produto, mov.localizacao_origem, -mov.quantidade)
        ant_dest, pos_dest = _atualizar_saldo_localizacao(produto, mov.localizacao_destino, mov.quantidade)
        mov.saldo_anterior_origem = ant_orig
        mov.saldo_posterior_origem = pos_orig
        mov.saldo_anterior_destino = ant_dest
        mov.saldo_posterior_destino = pos_dest

    seriais_finais = _processar_seriais_movimentacao(mov, seriais, novos_normalizados) if produto.controla_numero_serie else []

    if produto.controla_numero_serie:
        novo_total = produto.numeros_serie.filter(status='DISPONIVEL').count()
    else:
        novo_total = EstoqueLocalizacao.objects.filter(produto=produto).aggregate(
            total=Coalesce(Sum('quantidade'), 0)
        )['total']

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
    localizacao_origem=None,
    localizacao_destino=None,
    numeros_serie=None,
    numeros_serie_novos=None,
    pessoa=None,
    documento_referencia=None,
    motivo=None,
    observacoes=None,
    usuario=None,
):
    """Cria e aplica atomicamente uma movimentação de estoque completa com seriais."""
    mov = MovimentacaoEstoque(
        produto=produto,
        tipo=tipo,
        quantidade=quantidade,
        localizacao_origem=localizacao_origem,
        localizacao_destino=localizacao_destino,
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
    )
    mov.save()
    if seriais_finais:
        mov.numeros_serie.set(seriais_finais)
    return mov
