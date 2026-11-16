import re

from django.core.exceptions import ValidationError


def apenas_digitos(valor):
    """Remove todos os caracteres não numéricos de uma string."""
    if valor is None:
        return ''
    return re.sub(r'\D', '', str(valor))


def _calcular_dv_mod11(digitos_base, pesos):
    soma = sum(int(d) * p for d, p in zip(digitos_base, pesos))
    resto = soma % 11
    return '0' if resto < 2 else str(11 - resto)


def validar_digitos_cpf(digitos):
    """Valida se os 11 dígitos formam um CPF válido pelos dígitos verificadores."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    dv1 = _calcular_dv_mod11(digitos[:9], range(10, 1, -1))
    dv2 = _calcular_dv_mod11(digitos[:9] + dv1, range(11, 1, -1))
    return digitos[-2:] == dv1 + dv2


def validar_digitos_cnpj(digitos):
    """Valida se os 14 dígitos formam um CNPJ válido pelos dígitos verificadores."""
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _calcular_dv_mod11(digitos[:12], pesos_1)
    dv2 = _calcular_dv_mod11(digitos[:12] + dv1, pesos_2)
    return digitos[-2:] == dv1 + dv2


def validar_cpf_cnpj(valor):
    """Valida formato e dígitos verificadores de CPF (11 dígitos) ou CNPJ (14 dígitos)."""
    if valor is None or not str(valor).strip():
        return
    digitos = apenas_digitos(valor)
    if len(digitos) == 11:
        if not validar_digitos_cpf(digitos):
            raise ValidationError('CPF inválido. Verifique os dígitos informados.')
        return
    if len(digitos) == 14:
        if not validar_digitos_cnpj(digitos):
            raise ValidationError('CNPJ inválido. Verifique os dígitos informados.')
        return
    raise ValidationError('CPF deve conter 11 dígitos ou CNPJ deve conter 14 dígitos.')


def formatar_cpf_cnpj(valor):
    """Aplica máscara padrão de CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    digitos = apenas_digitos(texto)
    if len(digitos) == 11:
        return f'{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}'
    if len(digitos) == 14:
        return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'
    return texto


def validar_cep(valor):
    """Valida se o CEP possui exatamente 8 dígitos numéricos."""
    if valor is None or not str(valor).strip():
        return
    digitos = apenas_digitos(valor)
    if len(digitos) != 8 or len(set(digitos)) == 1:
        raise ValidationError('CEP inválido. Informe 8 dígitos numéricos (ex: 01001-000).')


def formatar_cep(valor):
    """Aplica máscara padrão de CEP (00000-000)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    digitos = apenas_digitos(texto)
    if len(digitos) == 8:
        return f'{digitos[:5]}-{digitos[5:]}'
    return texto


def formatar_telefone(valor):
    """Aplica máscara padrão brasileira de telefone fixo ou celular."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    digitos = apenas_digitos(texto)
    if len(digitos) == 10:
        return f'({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}'
    if len(digitos) == 11:
        return f'({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}'
    return texto


def validar_consistencia_pessoa(juridica_fisica, cnpj_cpf):
    """Garante compatibilidade entre Pessoa Física/Jurídica e CPF/CNPJ."""
    if juridica_fisica is None or not cnpj_cpf:
        return
    digitos = apenas_digitos(cnpj_cpf)
    if juridica_fisica == 1 and len(digitos) != 11:
        raise ValidationError({'cnpj_cpf': 'Pessoa Física exige um CPF válido com 11 dígitos.'})
    if juridica_fisica == 0 and len(digitos) != 14:
        raise ValidationError({'cnpj_cpf': 'Pessoa Jurídica exige um CNPJ válido com 14 dígitos.'})

