import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from unidecode import unidecode

from cadastro.models import Estado, Cidade


ESTADOS_IBGE = (
    (11, 'RO', 'Rondônia', 'NORTE', '1100205'),
    (12, 'AC', 'Acre', 'NORTE', '1200401'),
    (13, 'AM', 'Amazonas', 'NORTE', '1302603'),
    (14, 'RR', 'Roraima', 'NORTE', '1400100'),
    (15, 'PA', 'Pará', 'NORTE', '1501402'),
    (16, 'AP', 'Amapá', 'NORTE', '1600303'),
    (17, 'TO', 'Tocantins', 'NORTE', '1721000'),
    (21, 'MA', 'Maranhão', 'NORDESTE', '2111300'),
    (22, 'PI', 'Piauí', 'NORDESTE', '2211001'),
    (23, 'CE', 'Ceará', 'NORDESTE', '2304400'),
    (24, 'RN', 'Rio Grande do Norte', 'NORDESTE', '2408102'),
    (25, 'PB', 'Paraíba', 'NORDESTE', '2507507'),
    (26, 'PE', 'Pernambuco', 'NORDESTE', '2611606'),
    (27, 'AL', 'Alagoas', 'NORDESTE', '2704302'),
    (28, 'SE', 'Sergipe', 'NORDESTE', '2800308'),
    (29, 'BA', 'Bahia', 'NORDESTE', '2927408'),
    (31, 'MG', 'Minas Gerais', 'SUDESTE', '3106200'),
    (32, 'ES', 'Espírito Santo', 'SUDESTE', '3205309'),
    (33, 'RJ', 'Rio de Janeiro', 'SUDESTE', '3304557'),
    (35, 'SP', 'São Paulo', 'SUDESTE', '3550308'),
    (41, 'PR', 'Paraná', 'SUL', '4106902'),
    (42, 'SC', 'Santa Catarina', 'SUL', '4205407'),
    (43, 'RS', 'Rio Grande do Sul', 'SUL', '4314902'),
    (50, 'MS', 'Mato Grosso do Sul', 'CENTRO-OESTE', '5002704'),
    (51, 'MT', 'Mato Grosso', 'CENTRO-OESTE', '5103403'),
    (52, 'GO', 'Goiás', 'CENTRO-OESTE', '5208707'),
    (53, 'DF', 'Distrito Federal', 'CENTRO-OESTE', '5300108'),
)

CAPITAIS_IBGE = {item[4] for item in ESTADOS_IBGE}


class Command(BaseCommand):
    help = 'Importa os 27 estados brasileiros e os municípios a partir do arquivo JSON do IBGE.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--arquivo',
            type=str,
            default=str(Path(settings.BASE_DIR) / 'todas_as_cidades.json'),
            help='Caminho para o arquivo JSON de cidades (padrão: todas_as_cidades.json).'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        caminho_arquivo = Path(options['arquivo'])
        if not caminho_arquivo.exists():
            raise CommandError(f'Arquivo não encontrado: {caminho_arquivo}')

        with caminho_arquivo.open('r', encoding='utf-8') as arquivo:
            cidades_json = json.load(arquivo)

        estados_por_codigo = {}
        estados_criados = 0
        estados_atualizados = 0

        for codigo_uf, uf_sigla, nome_estado, regiao, _ in ESTADOS_IBGE:
            estado_obj, created = Estado.objects.update_or_create(
                codigoUf=codigo_uf,
                defaults={
                    'uf': unidecode(uf_sigla).upper(),
                    'estado': unidecode(nome_estado).upper(),
                    'regiao': unidecode(regiao).upper(),
                }
            )
            estados_por_codigo[codigo_uf] = estado_obj
            if created:
                estados_criados += 1
            else:
                estados_atualizados += 1

        existentes_por_ibge = {
            codigo: pk
            for codigo, pk in Cidade.objects.exclude(codigoIbge__isnull=True).values_list('codigoIbge', 'id')
        }

        novas_cidades = []
        cidades_para_atualizar = []
        ignoradas = 0

        for item in cidades_json:
            codigo_ibge = str(item.get('codigoIbge') or '').strip() or None
            codigo_uf = item.get('uf')
            estado_obj = estados_por_codigo.get(codigo_uf)

            if not estado_obj or not codigo_ibge:
                ignoradas += 1
                continue

            nome_bruto = item.get('descricaoCidade') or ''
            descricao_cidade = unidecode(nome_bruto).upper().strip()
            descricao_completa = f'{descricao_cidade} / {estado_obj.uf}' if descricao_cidade else None
            is_capital = bool(item.get('capital')) or (codigo_ibge in CAPITAIS_IBGE)

            if codigo_ibge in existentes_por_ibge:
                cidades_para_atualizar.append(
                    Cidade(
                        id=existentes_por_ibge[codigo_ibge],
                        descricaoCidade=descricao_cidade,
                        descricao_completa=descricao_completa,
                        uf=estado_obj,
                        latitude=item.get('latitude'),
                        longitude=item.get('longitude'),
                        capital=is_capital,
                        ddd=item.get('ddd'),
                        fusoHorario=item.get('fusoHorario'),
                        codigoIbge=codigo_ibge,
                    )
                )
            else:
                novas_cidades.append(
                    Cidade(
                        descricaoCidade=descricao_cidade,
                        descricao_completa=descricao_completa,
                        uf=estado_obj,
                        latitude=item.get('latitude'),
                        longitude=item.get('longitude'),
                        capital=is_capital,
                        ddd=item.get('ddd'),
                        fusoHorario=item.get('fusoHorario'),
                        codigoIbge=codigo_ibge,
                    )
                )

        if novas_cidades:
            Cidade.objects.bulk_create(novas_cidades, batch_size=1000)

        if cidades_para_atualizar:
            Cidade.objects.bulk_update(
                cidades_para_atualizar,
                fields=[
                    'descricaoCidade', 'descricao_completa', 'uf',
                    'latitude', 'longitude', 'capital', 'ddd', 'fusoHorario'
                ],
                batch_size=1000,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Importação concluída! '
                f'Estados -> criados: {estados_criados}, atualizados: {estados_atualizados}. '
                f'Cidades -> criadas: {len(novas_cidades)}, atualizadas: {len(cidades_para_atualizar)}'
                + (f', ignoradas: {ignoradas}' if ignoradas else '')
            )
        )

