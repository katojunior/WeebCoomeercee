import zoneinfo
from decimal import Decimal
from datetime import datetime, time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from unidecode import unidecode

try:
    import firebirdsql
except ImportError:
    firebirdsql = None

from cadastro.models import Pessoas
from cadastro_produto.models import Produtos
from vendas.models import Venda, ItemVenda


class Command(BaseCommand):
    help = 'Importa histórico de vendas e itens de vendas do banco Firebird (.FDB).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--arquivo',
            type=str,
            default=str(Path(settings.BASE_DIR) / 'INFYSK-ATUAL.FDB'),
            help='Caminho completo do arquivo de banco Firebird .FDB (padrão: INFYSK-ATUAL.FDB na raiz).'
        )
        parser.add_argument(
            '--host',
            type=str,
            default='localhost',
            help='Host do servidor Firebird (padrão: localhost).'
        )
        parser.add_argument(
            '--porta',
            type=int,
            default=3050,
            help='Porta do servidor Firebird (padrão: 3050).'
        )
        parser.add_argument(
            '--usuario',
            type=str,
            default='SYSDBA',
            help='Usuário do Firebird (padrão: SYSDBA).'
        )
        parser.add_argument(
            '--senha',
            type=str,
            default='masterkey',
            help='Senha do Firebird (padrão: masterkey).'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Tamanho do lote para inserção no PostgreSQL (padrão: 1000).'
        )
        parser.add_argument(
            '--limpar',
            action='store_true',
            help='Remove registros existentes nas tabelas de vendas antes de importar.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Executa toda a leitura, validação e mapeamento sem salvar nada no banco de dados.'
        )

    def handle(self, *args, **options):
        if firebirdsql is None:
            raise CommandError('O pacote firebirdsql não está instalado. Instale com: pip install firebirdsql')

        caminho_arquivo = Path(options['arquivo'])
        if not caminho_arquivo.exists():
            raise CommandError(f'Arquivo Firebird não encontrado: {caminho_arquivo}')

        host = options['host']
        porta = options['porta']
        usuario = options['usuario']
        senha = options['senha']
        batch_size = options['batch_size']
        limpar = options['limpar']
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO DE HISTÓRICO DE VENDAS (FIREBIRD -> DJANGO) ==='))
        self.stdout.write(f'Arquivo: {caminho_arquivo}')
        self.stdout.write(f'Conexão: {host}:{porta} (Usuário: {usuario})')
        if dry_run:
            self.stdout.write(self.style.WARNING('[MODO DRY-RUN ATIVADO: Nenhuma alteração será salva no PostgreSQL]'))

        # Cache de pessoas e produtos existentes
        self.stdout.write('Carregando cadastro de Pessoas e Produtos do PostgreSQL...')
        pessoas_ids = set(Pessoas.objects.values_list('id', flat=True))
        produtos_ids = set(Produtos.objects.values_list('id', flat=True))
        self.stdout.write(f'  Pessoas carregadas: {len(pessoas_ids)}')
        self.stdout.write(f'  Produtos carregados: {len(produtos_ids)}')

        tz = zoneinfo.ZoneInfo(getattr(settings, 'TIME_ZONE', 'America/Sao_Paulo'))

        # Conectar ao Firebird
        self.stdout.write('Conectando ao banco Firebird...')
        try:
            conn = firebirdsql.connect(
                host=host,
                port=porta,
                database=str(caminho_arquivo),
                user=usuario,
                password=senha,
                charset='WIN1252',
            )
        except Exception as e:
            raise CommandError(f'Falha ao conectar ao Firebird: {e}')

        cur = conn.cursor()

        # 1. Leitura de VENDAS
        self.stdout.write('Lendo tabela VENDAS do Firebird...')
        cur.execute("""
            SELECT
                CODIGO_VENDA,
                CODIGO_CLIENTE,
                CODIGO_TIPO_VENDA,
                DATA_VENDA,
                VALOR_TOTAL,
                COTACAO_DOLAR,
                PREVISAO_ENTREGA,
                DATA,
                HORA,
                OBS,
                OBS_OK,
                USUARIO,
                USUARIO_ATUALIZOU,
                DATA_HORA,
                DATA_HORA_ATUALIZADA,
                VALOR,
                DESCONTO,
                TOTAL_RECEBIDO_DINHEIRO,
                TOTAL_RECEBIDO_CHEQUE,
                TOTAL_RECEBIDO_BOLETO,
                TOTAL_RECEBIDO_CARTAO,
                TOTAL_RECEBIDO_PROMISSORIA,
                TOTAL_RECEBIDO_OUTROS,
                TOTAL_RECEBIDO_FINAL,
                NUMERO_NF,
                NUMERO_CF,
                DATA_FINALIZADA,
                TROCO,
                HORA_FINALIZADA,
                OBS_NF,
                ANOTACOES
            FROM VENDAS
            ORDER BY CODIGO_VENDA
        """)
        vendas_fb = cur.fetchall()
        self.stdout.write(f'Total de vendas encontradas no Firebird: {len(vendas_fb)}')

        # 2. Leitura de ITENS_VENDAS
        self.stdout.write('Lendo tabela ITENS_VENDAS do Firebird...')
        cur.execute("""
            SELECT
                CODIGO_ITENS_VENDAS,
                CODIGO_PRODUTO,
                CODIGO_VENDA,
                CODIGO_SEQUENCIA,
                QUANTIDADE,
                VALOR_UNITARIO,
                VALOR_TOTAL,
                USUARIO,
                USUARIO_ATUALIZOU,
                DATA_HORA,
                DATA_HORA_ATUALIZADA
            FROM ITENS_VENDAS
            ORDER BY CODIGO_ITENS_VENDAS
        """)
        itens_fb = cur.fetchall()
        self.stdout.write(f'Total de itens de vendas encontrados no Firebird: {len(itens_fb)}')

        cur.close()
        conn.close()

        def parse_data_hora(d_dt, d_data, d_hora):
            if isinstance(d_dt, datetime):
                if timezone.is_naive(d_dt):
                    return timezone.make_aware(d_dt, tz)
                return d_dt
            if d_data:
                h = d_hora if isinstance(d_hora, time) else time.min
                dt = datetime.combine(d_data, h)
                return timezone.make_aware(dt, tz)
            return None

        status_map = {
            0: 'ORCAMENTO',
            1: 'ABERTO',
            3: 'FINALIZADO',
        }

        # Processar Vendas
        vendas_instances = []
        vendas_ids_set = set()
        stats_status = {'ORCAMENTO': 0, 'ABERTO': 0, 'FINALIZADO': 0, 'CANCELADO': 0}
        total_subtotal_geral = Decimal('0.00')
        total_desconto_geral = Decimal('0.00')
        total_valor_geral = Decimal('0.00')
        clientes_orfãos = 0

        for row in vendas_fb:
            (
                cod_venda, cod_cliente, cod_tipo, data_venda_raw, valor_total_raw,
                cotacao_dolar, previsao_entrega, data_raw, hora_raw, obs_raw, obs_ok,
                usuario_raw, usuario_atualizou_raw, data_hora_raw, data_hora_atualizada_raw,
                valor_raw, desconto_raw, rec_dinheiro, rec_cheque, rec_boleto, rec_cartao,
                rec_promissoria, rec_outros, rec_final, num_nf, num_cf, data_finalizada,
                troco, hora_finalizada, obs_nf, anotacoes
            ) = row

            status = status_map.get(cod_tipo, 'FINALIZADO')
            stats_status[status] = stats_status.get(status, 0) + 1

            # Resolver Data/Hora
            dt_venda = None
            if data_hora_raw:
                dt_venda = parse_data_hora(data_hora_raw, None, None)
            elif data_raw:
                dt_venda = parse_data_hora(None, data_raw, hora_raw)
            elif data_venda_raw:
                dt_venda = parse_data_hora(None, data_venda_raw, hora_raw)

            # Resolver Valores
            val_total = Decimal(str(valor_total_raw)) if valor_total_raw is not None else Decimal('0.00')
            desc = Decimal(str(desconto_raw)) if desconto_raw is not None else Decimal('0.00')
            subtot = Decimal(str(valor_raw)) if valor_raw is not None else (val_total + desc)

            total_subtotal_geral += subtot
            total_desconto_geral += desc
            total_valor_geral += val_total

            # Resolver Cliente
            cliente_id = None
            obs_extra = []
            if cod_cliente is not None:
                if cod_cliente in pessoas_ids:
                    cliente_id = cod_cliente
                else:
                    clientes_orfãos += 1
                    obs_extra.append(f"[Cliente Firebird ID {cod_cliente} não encontrado no cadastro]")

            # Resolver Forma de Pagamento
            pagamentos = []
            if rec_dinheiro and Decimal(str(rec_dinheiro)) > Decimal('0.00'):
                pagamentos.append(f"Dinheiro: R$ {Decimal(str(rec_dinheiro)):.2f}")
            if rec_cartao and Decimal(str(rec_cartao)) > Decimal('0.00'):
                pagamentos.append(f"Cartão: R$ {Decimal(str(rec_cartao)):.2f}")
            if rec_cheque and Decimal(str(rec_cheque)) > Decimal('0.00'):
                pagamentos.append(f"Cheque: R$ {Decimal(str(rec_cheque)):.2f}")
            if rec_boleto and Decimal(str(rec_boleto)) > Decimal('0.00'):
                pagamentos.append(f"Boleto: R$ {Decimal(str(rec_boleto)):.2f}")
            if rec_promissoria and Decimal(str(rec_promissoria)) > Decimal('0.00'):
                pagamentos.append(f"Promissória: R$ {Decimal(str(rec_promissoria)):.2f}")
            if rec_outros and Decimal(str(rec_outros)) > Decimal('0.00'):
                pagamentos.append(f"Outros: R$ {Decimal(str(rec_outros)):.2f}")
            forma_pagto = ", ".join(pagamentos) if pagamentos else None

            # Observações consolidadas
            partes_obs = []
            if obs_raw and str(obs_raw).strip():
                partes_obs.append(str(obs_raw).strip())
            if obs_nf and str(obs_nf).strip():
                partes_obs.append(f"[Obs NF: {str(obs_nf).strip()}]")
            if anotacoes and str(anotacoes).strip():
                partes_obs.append(f"[Anotações: {str(anotacoes).strip()}]")
            if obs_extra:
                partes_obs.extend(obs_extra)
            obs_final = "\n".join(partes_obs) if partes_obs else None

            # NF / CF
            nf_clean = str(num_nf).strip() if num_nf and str(num_nf).strip() else None
            cf_clean = str(num_cf).strip() if num_cf and str(num_cf).strip() else None

            # Auditoria
            dt_auditoria = dt_venda or timezone.now()
            dt_auditoria_atu = parse_data_hora(data_hora_atualizada_raw, None, None) or dt_auditoria
            usr = str(usuario_raw).strip() if usuario_raw else None
            usr_atu = str(usuario_atualizou_raw).strip() if usuario_atualizou_raw else usr

            venda_obj = Venda(
                id=cod_venda,
                cliente_id=cliente_id,
                vendedor=None,
                status=status,
                data_venda=dt_venda,
                subtotal=subtot,
                desconto=desc,
                valor_total=val_total,
                forma_pagamento=forma_pagto,
                numero_nf=nf_clean,
                numero_cupom_fiscal=cf_clean,
                observacoes=obs_final,
                usuario=usr,
                usuario_atualizou=usr_atu,
                data_hora=dt_auditoria,
                data_hora_atualizada=dt_auditoria_atu,
            )
            vendas_instances.append(venda_obj)
            vendas_ids_set.add(cod_venda)

        # Processar Itens de Vendas
        itens_instances = []
        produtos_desconhecidos = 0

        for row in itens_fb:
            (
                cod_item, cod_prod, cod_venda, cod_seq, qtd_raw,
                val_unit_raw, val_tot_raw, usr_raw, usr_atu_raw,
                dt_hr_raw, dt_hr_atu_raw
            ) = row

            if cod_venda not in vendas_ids_set:
                continue

            if cod_prod not in produtos_ids:
                produtos_desconhecidos += 1
                continue

            qtd = Decimal(str(qtd_raw)) if qtd_raw is not None else Decimal('1.000')
            val_unit = Decimal(str(val_unit_raw)) if val_unit_raw is not None else Decimal('0.00')
            val_tot = Decimal(str(val_tot_raw)) if val_tot_raw is not None else (qtd * val_unit).quantize(Decimal('0.01'))
            seq = int(cod_seq) if cod_seq is not None else 1

            dt_item = parse_data_hora(dt_hr_raw, None, None) or timezone.now()
            dt_item_atu = parse_data_hora(dt_hr_atu_raw, None, None) or dt_item
            u_item = str(usr_raw).strip() if usr_raw else None
            u_item_atu = str(usr_atu_raw).strip() if usr_atu_raw else u_item

            item_obj = ItemVenda(
                id=cod_item,
                venda_id=cod_venda,
                produto_id=cod_prod,
                sequencia=seq,
                quantidade=qtd,
                valor_unitario=val_unit,
                desconto_unitario=Decimal('0.00'),
                valor_total=val_tot,
                usuario=u_item,
                usuario_atualizou=u_item_atu,
                data_hora=dt_item,
                data_hora_atualizada=dt_item_atu,
            )
            itens_instances.append(item_obj)

        with transaction.atomic():
            if limpar and not dry_run:
                self.stdout.write(self.style.WARNING('Limpando registros existentes no app vendas...'))
                ItemVenda.objects.all().delete()
                Venda.objects.all().delete()

            if not dry_run:
                self.stdout.write(f'Gravando {len(vendas_instances)} vendas no PostgreSQL...')
                Venda.objects.bulk_create(vendas_instances, batch_size=batch_size)

                self.stdout.write(f'Gravando {len(itens_instances)} itens de venda no PostgreSQL...')
                ItemVenda.objects.bulk_create(itens_instances, batch_size=batch_size)

                # Sincronizar sequências no PostgreSQL
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('vendas_venda', 'id'),
                            COALESCE((SELECT MAX(id) FROM vendas_venda), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('vendas_itemvenda', 'id'),
                            COALESCE((SELECT MAX(id) FROM vendas_itemvenda), 1)
                        );
                    """)

        # Resumo final
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- ESTATÍSTICAS DA IMPORTAÇÃO DE VENDAS ---'))
        self.stdout.write(f'  Vendas Processadas            : {len(vendas_instances)}')
        self.stdout.write(f'    - Finalizadas               : {stats_status["FINALIZADO"]}')
        self.stdout.write(f'    - Orçamentos                : {stats_status["ORCAMENTO"]}')
        self.stdout.write(f'    - Em Aberto                 : {stats_status["ABERTO"]}')
        self.stdout.write(f'    - Canceladas                : {stats_status["CANCELADO"]}')
        self.stdout.write(f'  Itens de Vendas Processados   : {len(itens_instances)}')
        self.stdout.write(f'  Clientes órfãos mapeados      : {clientes_orfãos}')
        self.stdout.write(f'  Produtos desconhecidos        : {produtos_desconhecidos}')
        self.stdout.write(f'  Subtotal Geral Faturado       : R$ {total_subtotal_geral:,.2f}')
        self.stdout.write(f'  Descontos Concedidos          : R$ {total_desconto_geral:,.2f}')
        self.stdout.write(f'  Valor Total Geral Líquido     : R$ {total_valor_geral:,.2f}')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n[DRY-RUN] Simulação concluída com sucesso! Nenhum registro foi inserido.'))
            return

        total_v = Venda.objects.count()
        total_iv = ItemVenda.objects.count()
        self.stdout.write(self.style.SUCCESS('\nIMPORTAÇÃO DE VENDAS CONCLUÍDA COM SUCESSO!'))
        self.stdout.write(self.style.SUCCESS(f'Total de vendas no banco: {total_v}'))
        self.stdout.write(self.style.SUCCESS(f'Total de itens de venda no banco: {total_iv}'))

