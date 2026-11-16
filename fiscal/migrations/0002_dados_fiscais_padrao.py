from django.db import migrations


CFOPS_PADRAO = [
    ('1102', 'COMPRA PARA COMERCIALIZACAO', 'ENTRADA', True),
    ('1202', 'DEVOLUCAO DE VENDA DE MERCADORIA ADQUIRIDA DE TERCEIROS', 'ENTRADA', True),
    ('1403', 'COMPRA PARA COMERCIALIZACAO EM OPERACAO COM MERCADORIA SUJEITA A ST', 'ENTRADA', True),
    ('1949', 'OUTRA ENTRADA DE MERCADORIA OU PRESTACAO DE SERVICO NAO ESPECIFICADA', 'ENTRADA', True),
    ('2102', 'COMPRA PARA COMERCIALIZACAO INTERESTADUAL', 'ENTRADA', True),
    ('2403', 'COMPRA PARA COMERCIALIZACAO INTERESTADUAL COM ST', 'ENTRADA', True),
    ('5102', 'VENDA DE MERCADORIA ADQUIRIDA OU RECEBIDA DE TERCEIROS', 'SAIDA', True),
    ('5202', 'DEVOLUCAO DE COMPRA PARA COMERCIALIZACAO', 'SAIDA', True),
    ('5405', 'VENDA DE MERCADORIA ADQUIRIDA OU RECEBIDA DE TERCEIROS COM ST', 'SAIDA', True),
    ('5910', 'REMESSA EM BONIFICACAO, DOACAO OU BRINDE', 'SAIDA', True),
    ('5915', 'REMESSA DE MERCADORIA OU BEM PARA CONSERTO OU REPARO', 'SAIDA', False),
    ('5949', 'OUTRA SAIDA DE MERCADORIA OU PRESTACAO DE SERVICO NAO ESPECIFICADA', 'SAIDA', True),
    ('6102', 'VENDA DE MERCADORIA ADQUIRIDA OU RECEBIDA DE TERCEIROS INTERESTADUAL', 'SAIDA', True),
    ('6108', 'VENDA DE MERCADORIA ADQUIRIDA PARA NAO CONTRIBUINTE INTERESTADUAL', 'SAIDA', True),
    ('6404', 'VENDA DE MERCADORIA SUJEITA A ST COMO CONTRIBUINTE SUBSTITUTO', 'SAIDA', True),
]

NCMS_INFORMATICA = [
    ('84713019', 'MAQUINAS AUTOMATICAS PARA PROCESSAMENTO DE DADOS PORTATEIS (NOTEBOOKS)'),
    ('84714100', 'OUTRAS MAQUINAS AUTOMATICAS PARA PROCESSAMENTO DE DADOS (DESKTOPS)'),
    ('84715010', 'UNIDADES DE PROCESSAMENTO DIGITAL DE PEQUENA CAPACIDADE'),
    ('84716052', 'TECLADOS PARA MAQUINAS AUTOMATICAS PARA PROCESSAMENTO DE DADOS'),
    ('84716053', 'INDICADORES OU APONTADORES (MOUSES E TRACKBALLS)'),
    ('84717012', 'UNIDADES DE DISCOS RIGIDOS (HD)'),
    ('84717040', 'UNIDADES DE MEMORIA EM ESTADO SOLIDO (SSD)'),
    ('84733019', 'GABINETES E SUAS PARTES PARA COMPUTADORES'),
    ('84733041', 'PLACAS-MAE PARA MAQUINAS DE PROCESSAMENTO DE DADOS'),
    ('84733042', 'MODULOS DE MEMORIA RAM'),
    ('84733043', 'PLACAS DE VIDEO E PROCESSADORES GRAFICOS'),
    ('85044090', 'FONTES DE ALIMENTACAO E CARREGADORES'),
    ('85176294', 'ROTEADORES E SWITCHES PARA REDES DE DADOS'),
    ('85285220', 'MONITORES POLICROMATICOS PARA COMPUTADOR'),
    ('85444200', 'CABOS ELETRICOS E DE DADOS COM CONECTORES (HDMI, USB, REDE)'),
]

CESTS_INFORMATICA = [
    ('2102800', 'MAQUINAS AUTOMATICAS PARA PROCESSAMENTO DE DADOS PORTATEIS (NCM 8471.30)'),
    ('2102900', 'OUTRAS MAQUINAS AUTOMATICAS PARA PROCESSAMENTO DE DADOS (NCM 8471.41)'),
    ('2103000', 'UNIDADES DE PROCESSAMENTO DIGITAL DE DADOS (NCM 8471.50)'),
    ('2103100', 'TECLADOS, MOUSES E UNIDADES DE ENTRADA OU SAIDA (NCM 8471.60)'),
    ('2103200', 'UNIDADES DE MEMORIA, DISCOS RIGIDOS E SSD (NCM 8471.70)'),
    ('2103300', 'PLACAS-MAE, MEMORIAS RAM, PLACAS DE VIDEO E PARTES (NCM 8473.30)'),
    ('2106300', 'MONITORES E PROJETORES PARA COMPUTADOR (NCM 8528.52)'),
    ('2109800', 'FONTES DE ALIMENTACAO PARA COMPUTADORES (NCM 8504.40)'),
]


def popular_dados_fiscais(apps, schema_editor):
    """Popula CFOPs padrão de varejo e NCMs/CESTs comuns de informática."""
    Cfop = apps.get_model('fiscal', 'Cfop')
    Ncm = apps.get_model('fiscal', 'Ncm')
    Cest = apps.get_model('fiscal', 'Cest')

    for codigo, descricao, tipo_operacao, movimenta_estoque in CFOPS_PADRAO:
        Cfop.objects.update_or_create(
            codigo=codigo,
            defaults={
                'descricao': descricao,
                'tipo_operacao': tipo_operacao,
                'movimenta_estoque': movimenta_estoque,
                'ativo': True,
            },
        )

    for codigo, descricao in NCMS_INFORMATICA:
        Ncm.objects.update_or_create(
            codigo=codigo,
            defaults={'descricao': descricao, 'ativo': True},
        )

    for codigo, descricao in CESTS_INFORMATICA:
        Cest.objects.update_or_create(
            codigo=codigo,
            defaults={'descricao': descricao, 'ativo': True},
        )


def remover_dados_fiscais(apps, schema_editor):
    """Remove os registros iniciais caso a migration seja revertida."""
    Cfop = apps.get_model('fiscal', 'Cfop')
    Ncm = apps.get_model('fiscal', 'Ncm')
    Cest = apps.get_model('fiscal', 'Cest')

    Cfop.objects.filter(codigo__in=[item[0] for item in CFOPS_PADRAO]).delete()
    Ncm.objects.filter(codigo__in=[item[0] for item in NCMS_INFORMATICA]).delete()
    Cest.objects.filter(codigo__in=[item[0] for item in CESTS_INFORMATICA]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fiscal', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(popular_dados_fiscais, remover_dados_fiscais),
    ]

