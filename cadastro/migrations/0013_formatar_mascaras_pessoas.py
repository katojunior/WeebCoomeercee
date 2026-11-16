from django.db import migrations

from cadastro.validators import formatar_cep, formatar_cpf_cnpj, formatar_telefone


def formatar_pessoas_existentes(apps, schema_editor):
    """Aplica máscaras padronizadas aos registros de Pessoas já cadastrados."""
    Pessoas = apps.get_model('cadastro', 'Pessoas')
    for pessoa in Pessoas.objects.all():
        alterados = []
        formatacoes = (
            ('cnpj_cpf', formatar_cpf_cnpj(pessoa.cnpj_cpf)),
            ('cep', formatar_cep(pessoa.cep)),
            ('celular', formatar_telefone(pessoa.celular)),
            ('telefone', formatar_telefone(pessoa.telefone)),
            ('telefone2', formatar_telefone(pessoa.telefone2)),
        )
        for campo, novo_valor in formatacoes:
            if getattr(pessoa, campo) != novo_valor:
                setattr(pessoa, campo, novo_valor)
                alterados.append(campo)
        if alterados:
            pessoa.save(update_fields=alterados)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastro', '0012_alter_pessoas_celular_alter_pessoas_cep_and_more'),
    ]

    operations = [
        migrations.RunPython(formatar_pessoas_existentes, migrations.RunPython.noop),
    ]

