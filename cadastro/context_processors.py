from .models import Empresa


def empresa_context(request):
    """
    Disponibiliza a Empresa principal ativa e os dados formatados de cabeçalho
    de impressão em todos os templates do sistema (`{{ empresa_atual }}` e `{{ cabecalho_impressao }}`).
    """
    try:
        empresa = Empresa.get_principal()
    except Exception:
        empresa = None

    return {
        'empresa_atual': empresa,
        'cabecalho_impressao': empresa.dados_cabecalho_impressao if empresa else {},
    }
