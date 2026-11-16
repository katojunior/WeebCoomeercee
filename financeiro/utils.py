from decimal import Decimal, ROUND_HALF_UP


CONDICAO_PAGAMENTO_CHOICES = (
    ('DINHEIRO', 'Dinheiro (À Vista)'),
    ('PIX', 'PIX (À Vista)'),
    ('CARTAO_DEBITO', 'Cartão de Débito (À Vista)'),
    ('CARTAO_CREDITO', 'Cartão de Crédito'),
    ('BOLETO', 'Boleto Bancário'),
    ('CREDIARIO', 'Crediário / Promissória (A Prazo)'),
    ('TRANSFERENCIA', 'Transferência Bancária'),
    ('OUTROS', 'Outros'),
)


def money(valor):
    """Arredonda para 2 casas decimais no padrão financeiro (ROUND_HALF_UP)."""
    if valor is None:
        return Decimal('0.00')
    return Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def dividir_valor(total, n):
    """
    Divide um valor total em 'n' parcelas com precisão contábil.
    A última parcela absorve qualquer resíduo de arredondamento de centavos,
    garantindo que sum(parcelas) == total exato.
    """
    total_dec = money(total)
    num = int(n) if n else 1
    if num <= 1:
        return [total_dec]

    por_parcela = (total_dec / num).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    ultima = money(total_dec - por_parcela * (num - 1))
    return [por_parcela] * (num - 1) + [ultima]
