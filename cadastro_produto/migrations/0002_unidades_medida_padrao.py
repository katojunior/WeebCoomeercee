from django.db import migrations


UNIDADES_PADRAO = [
    ('UN', 'UNIDADE', False),
    ('PC', 'PECA', False),
    ('CX', 'CAIXA', False),
    ('KIT', 'KIT', False),
    ('PAR', 'PAR', False),
    ('MT', 'METRO', True),
    ('KG', 'QUILOGRAMA', True),
]


def criar_unidades_padrao(apps, schema_editor):
    """Popula as unidades de medida padrão no banco de dados."""
    UnidadeMedida = apps.get_model('cadastro_produto', 'UnidadeMedida')
    for sigla, descricao, permite_fracionado in UNIDADES_PADRAO:
        UnidadeMedida.objects.update_or_create(
            sigla=sigla,
            defaults={
                'descricao': descricao,
                'permite_fracionado': permite_fracionado,
                'ativo': True,
            },
        )


def remover_unidades_padrao(apps, schema_editor):
    """Remove as unidades de medida padrão ao reverter a migration."""
    UnidadeMedida = apps.get_model('cadastro_produto', 'UnidadeMedida')
    siglas = [item[0] for item in UNIDADES_PADRAO]
    UnidadeMedida.objects.filter(sigla__in=siglas).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cadastro_produto', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_unidades_padrao, remover_unidades_padrao),
    ]

