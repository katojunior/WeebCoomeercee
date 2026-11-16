import zoneinfo
from decimal import Decimal
from datetime import datetime, time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction, models
from django.utils import timezone
from unidecode import unidecode

try:
    import firebirdsql
except ImportError:
    firebirdsql = None

from ordem_servico.models import EquipamentoCliente, OrdemServico, ItemOrdemServico
from cadastro_produto.models import Produtos


class Command(BaseCommand):
    help = 'Importa equipamentos de clientes e ordens de serviço (com peças e laudos técnicos) do Firebird (.FDB).'

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
            help='Remove registros existentes nas tabelas do app ordem_servico antes de importar.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Executa toda a leitura, validação e mapeamento sem salvar nada no banco de dados.'
        )

    def handle(self, *args, **options):
        if firebirdsql is None:
            raise CommandError('O pacote firebirdsql não está instalado. Instale com: pip install firebirdsql passlib')

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

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO DE ORDENS DE SERVIÇO E EQUIPAMENTOS (FIREBIRD -> DJANGO) ==='))
        self.stdout.write(f'Arquivo: {caminho_arquivo}')
        self.stdout.write(f'Conexão: {host}:{porta} (Usuário: {usuario})')
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN ATIVADO: Nenhuma alteração será gravada no banco.'))

        # Conectar ao Firebird
        try:
            conn = firebirdsql.connect(
                host=host,
                port=porta,
                database=str(caminho_arquivo.resolve()),
                user=usuario,
                password=senha,
                charset='WIN1252'
            )
        except Exception as e:
            raise CommandError(f'Falha ao conectar no Firebird: {e}')

        cur = conn.cursor()

        # 1. Carregar EQUIPAMENTOS
        self.stdout.write('Carregando equipamentos de clientes (EQUIPAMENTOS)...')
        cur.execute("""
            SELECT 
                CODIGO_EQUIPAMENTO, CODIGO_CLIENTE, DESCRICAO_EQUIPAMENTO,
                DATA_CADASTRO, DATA_ULTIMO_RETORNO, VALOR, OBS,
                USUARIO, USUARIO_ATUALIZOU, DATA_HORA, DATA_HORA_ATUALIZADA,
                NUMERO_SERIE
            FROM EQUIPAMENTOS
            ORDER BY CODIGO_EQUIPAMENTO
        """)
        eq_rows = cur.fetchall()
        eq_cols = [d[0] for d in cur.description]
        self.stdout.write(f'Total de equipamentos encontrados: {len(eq_rows)}')

        # 2. Carregar ITENS_ORDENS (problemas e soluções dos equipamentos da OS)
        self.stdout.write('Carregando laudos técnicos e problemas (ITENS_ORDENS)...')
        cur.execute("""
            SELECT 
                CODIGO_ITENS_ORDENS, CODIGO_ORDEM, CODIGO_EQUIPAMENTO,
                DESCRICAO_PROBLEMA, SOLUCAO_APRESENTADA
            FROM ITENS_ORDENS
            ORDER BY CODIGO_ORDEM, CODIGO_ITENS_ORDENS
        """)
        io_rows = cur.fetchall()
        io_cols = [d[0] for d in cur.description]
        self.stdout.write(f'Total de laudos/itens de OS encontrados: {len(io_rows)}')

        io_by_ordem = {}
        for r in io_rows:
            row = dict(zip(io_cols, r))
            io_by_ordem.setdefault(row['CODIGO_ORDEM'], []).append(row)

        # 3. Carregar ORDENS
        self.stdout.write('Carregando ordens de serviço (ORDENS)...')
        cur.execute("""
            SELECT 
                CODIGO_ORDEM, CODIGO_CLIENTE, CODIGO_TIPO_ORDEM, CODIGO_FUNCIONARIO,
                PREVISAO_ENTREGA, HORA_ENTRADA, PECAS_TOTAL, VALOR_TOTAL,
                SERVICOS_TOTAL, DATA_ENTRADA, USUARIO, USUARIO_ATUALIZOU,
                DATA_HORA, DATA_HORA_ATUALIZADA, OBS_OK, PRE_FINALIZADA,
                DESCONTO, TROCO, TOTAL_RECEBIDO_DINHEIRO, TOTAL_RECEBIDO_CHEQUE,
                TOTAL_RECEBIDO_BOLETO, TOTAL_RECEBIDO_CARTAO, TOTAL_RECEBIDO_PROMISSORIA,
                TOTAL_PRAZO_A_RECEBER, TOTAL_RECEBIDO_FINAL, NUMERO_NF, NUMERO_CF,
                DATA_FINALIZADA, HORA_FINALIZADA, VALOR_TOTAL_FINAL
            FROM ORDENS
            ORDER BY CODIGO_ORDEM
        """)
        ordens_rows = cur.fetchall()
        ordens_cols = [d[0] for d in cur.description]
        self.stdout.write(f'Total de ordens de serviço encontradas: {len(ordens_rows)}')

        # 4. Carregar PECAS_ORDENS
        self.stdout.write('Carregando peças e serviços aplicados nas OS (PECAS_ORDENS)...')
        cur.execute("""
            SELECT 
                CODIGO_PECA_ORDEM, CODIGO_ORDEM, CODIGO_PRODUTO, VALOR_UNIT,
                CODIGO_ITENS_ORDENS, QUANTIDADE, PECAS_TOTAL,
                USUARIO, USUARIO_ATUALIZOU, DATA_HORA, DATA_HORA_ATUALIZADA
            FROM PECAS_ORDENS
            ORDER BY CODIGO_PECA_ORDEM
        """)
        pecas_rows = cur.fetchall()
        pecas_cols = [d[0] for d in cur.description]
        self.stdout.write(f'Total de peças e serviços em OS encontrados: {len(pecas_rows)}')

        conn.close()

        tz = timezone.get_current_timezone()

        # Cache de produtos de serviço para tipificação automática (PECA vs SERVICO)
        service_prod_ids = set(
            Produtos.objects.filter(
                models.Q(categoria__nome__icontains='SERVIC') |
                models.Q(nome__icontains='SERVIC') |
                models.Q(unidade_medida__sigla='SV')
            ).values_list('id', flat=True)
        )

        def combine_date_time(d_val, t_val):
            if not d_val:
                return None
            if not t_val:
                t_val = time(0, 0, 0)
            dt = datetime.combine(d_val, t_val)
            try:
                return timezone.make_aware(dt, tz)
            except Exception:
                return dt.replace(tzinfo=zoneinfo.ZoneInfo('America/Sao_Paulo'))

        def make_dt_aware(dt_val):
            if not dt_val:
                return None
            if timezone.is_naive(dt_val):
                try:
                    return timezone.make_aware(dt_val, tz)
                except Exception:
                    return dt_val.replace(tzinfo=zoneinfo.ZoneInfo('America/Sao_Paulo'))
            return dt_val

        with transaction.atomic():
            if limpar and not dry_run:
                self.stdout.write(self.style.WARNING('Limpando tabelas do app ordem_servico...'))
                ItemOrdemServico.objects.all().delete()
                OrdemServico.objects.all().delete()
                EquipamentoCliente.objects.all().delete()

            # 1. Processar e Inserir EQUIPAMENTOS
            equipamentos_instances = []
            for r in eq_rows:
                row = dict(zip(eq_cols, r))
                eq_id = row['CODIGO_EQUIPAMENTO']
                cliente_id = row['CODIGO_CLIENTE']
                desc = unidecode(str(row['DESCRICAO_EQUIPAMENTO'] or '')).upper().strip()[:150]
                if not desc:
                    desc = f'EQUIPAMENTO #{eq_id}'
                sn = unidecode(str(row['NUMERO_SERIE'] or '')).upper().strip()[:100] if row['NUMERO_SERIE'] else None
                obs = str(row['OBS'] or '').strip() or None

                dt_cad = row['DATA_CADASTRO']
                dt_hora = row['DATA_HORA'] or (datetime.combine(dt_cad, time(0, 0)) if dt_cad else None)
                data_hora = make_dt_aware(dt_hora)
                data_hora_atualizada = make_dt_aware(row['DATA_HORA_ATUALIZADA'])

                eq_obj = EquipamentoCliente(
                    id=eq_id,
                    cliente_id=cliente_id,
                    descricao=desc,
                    numero_serie=sn,
                    observacoes=obs,
                    ativo=True,
                    data_hora=data_hora,
                    data_hora_atualizada=data_hora_atualizada,
                    usuario=str(row['USUARIO'] or '').strip()[:50] or None,
                    usuario_atualizou=str(row['USUARIO_ATUALIZOU'] or '').strip()[:50] or None,
                )
                equipamentos_instances.append(eq_obj)

            if not dry_run:
                self.stdout.write(f'Gravando {len(equipamentos_instances)} equipamentos no PostgreSQL...')
                EquipamentoCliente.objects.bulk_create(equipamentos_instances, batch_size=batch_size)

            # 2. Processar e Inserir ORDENS
            ordens_instances = []
            io_to_eq_map = {}

            stats_status = {'ORCAMENTO': 0, 'AGUARDANDO': 0, 'FINALIZADO': 0}

            for r in ordens_rows:
                row = dict(zip(ordens_cols, r))
                ordem_id = row['CODIGO_ORDEM']
                cliente_id = row['CODIGO_CLIENTE']
                tecnico_id = row['CODIGO_FUNCIONARIO']
                tipo_ordem = row['CODIGO_TIPO_ORDEM']

                if tipo_ordem == 1:
                    status_os = 'ORCAMENTO'
                elif tipo_ordem == 2:
                    status_os = 'AGUARDANDO'
                else:
                    status_os = 'FINALIZADO'
                stats_status[status_os] += 1

                data_abertura = combine_date_time(row['DATA_ENTRADA'], row['HORA_ENTRADA'])
                data_conclusao = combine_date_time(row['DATA_FINALIZADA'], row['HORA_FINALIZADA'])
                previsao_entrega = row['PREVISAO_ENTREGA']

                val_pecas = Decimal(str(row['PECAS_TOTAL'] or 0)).quantize(Decimal('0.01'))
                val_serv = Decimal(str(row['SERVICOS_TOTAL'] or 0)).quantize(Decimal('0.01'))
                desconto = Decimal(str(row['DESCONTO'] or 0)).quantize(Decimal('0.01'))
                val_total = Decimal(str(row['VALOR_TOTAL_FINAL'] or row['VALOR_TOTAL'] or 0)).quantize(Decimal('0.01'))

                formas = []
                if row['TOTAL_RECEBIDO_DINHEIRO'] and Decimal(str(row['TOTAL_RECEBIDO_DINHEIRO'])) > 0:
                    formas.append('DINHEIRO')
                if row['TOTAL_RECEBIDO_CARTAO'] and Decimal(str(row['TOTAL_RECEBIDO_CARTAO'])) > 0:
                    formas.append('CARTAO')
                if row['TOTAL_RECEBIDO_CHEQUE'] and Decimal(str(row['TOTAL_RECEBIDO_CHEQUE'])) > 0:
                    formas.append('CHEQUE')
                if row['TOTAL_RECEBIDO_BOLETO'] and Decimal(str(row['TOTAL_RECEBIDO_BOLETO'])) > 0:
                    formas.append('BOLETO')
                if row['TOTAL_RECEBIDO_PROMISSORIA'] and Decimal(str(row['TOTAL_RECEBIDO_PROMISSORIA'])) > 0:
                    formas.append('PROMISSORIA')
                if row['TOTAL_PRAZO_A_RECEBER'] and Decimal(str(row['TOTAL_PRAZO_A_RECEBER'])) > 0:
                    formas.append('A PRAZO')

                forma_pagto = ' / '.join(formas)[:60] if formas else None

                ios = io_by_ordem.get(ordem_id, [])
                primary_eq_id = None
                defeitos = []
                solucoes = []
                for item in ios:
                    io_to_eq_map[item['CODIGO_ITENS_ORDENS']] = item['CODIGO_EQUIPAMENTO']
                    if not primary_eq_id and item['CODIGO_EQUIPAMENTO']:
                        primary_eq_id = item['CODIGO_EQUIPAMENTO']
                    prob = str(item['DESCRICAO_PROBLEMA'] or '').strip()
                    if prob and prob not in defeitos:
                        defeitos.append(prob)
                    sol = str(item['SOLUCAO_APRESENTADA'] or '').strip()
                    if sol and sol not in solucoes:
                        solucoes.append(sol)

                defeito_reclamado = '\n'.join(defeitos).strip() or None
                laudo_tecnico = '\n'.join(solucoes).strip() or None

                notes = []
                raw_obs_ok = str(row['OBS_OK'] or '').strip()
                if raw_obs_ok:
                    notes.append(raw_obs_ok)

                obs_interna = '\n'.join(notes).strip() or None

                os_obj = OrdemServico(
                    id=ordem_id,
                    cliente_id=cliente_id,
                    equipamento_id=primary_eq_id,
                    tecnico_id=tecnico_id,
                    status=status_os,
                    data_abertura=data_abertura or timezone.now(),
                    previsao_entrega=previsao_entrega,
                    data_conclusao=data_conclusao,
                    defeito_reclamado=defeito_reclamado,
                    laudo_tecnico=laudo_tecnico,
                    valor_pecas=val_pecas,
                    valor_servicos=val_serv,
                    desconto=desconto,
                    valor_total=val_total,
                    forma_pagamento=forma_pagto,
                    numero_nf=str(row['NUMERO_NF'] or '').strip()[:50] or None,
                    numero_cupom_fiscal=str(row['NUMERO_CF'] or '').strip()[:50] or None,
                    observacoes=obs_interna,
                    data_hora=make_dt_aware(row['DATA_HORA']),
                    data_hora_atualizada=make_dt_aware(row['DATA_HORA_ATUALIZADA']),
                    usuario=str(row['USUARIO'] or '').strip()[:50] or None,
                    usuario_atualizou=str(row['USUARIO_ATUALIZOU'] or '').strip()[:50] or None,
                )
                ordens_instances.append(os_obj)

            if not dry_run:
                self.stdout.write(f'Gravando {len(ordens_instances)} ordens de serviço no PostgreSQL...')
                OrdemServico.objects.bulk_create(ordens_instances, batch_size=batch_size)

            # 3. Processar e Inserir PECAS_ORDENS
            itens_instances = []
            for r in pecas_rows:
                row = dict(zip(pecas_cols, r))
                peca_id = row['CODIGO_PECA_ORDEM']
                ordem_id = row['CODIGO_ORDEM']
                prod_id = row['CODIGO_PRODUTO']
                io_id = row['CODIGO_ITENS_ORDENS']
                eq_id = io_to_eq_map.get(io_id)

                qtd = Decimal(str(row['QUANTIDADE'] or 1)).quantize(Decimal('0.001'))
                v_unit = Decimal(str(row['VALOR_UNIT'] or 0)).quantize(Decimal('0.01'))
                v_total = Decimal(str(row['PECAS_TOTAL'] or (qtd * v_unit))).quantize(Decimal('0.01'))

                tipo_item = 'SERVICO' if prod_id in service_prod_ids else 'PECA'

                item_obj = ItemOrdemServico(
                    id=peca_id,
                    ordem_id=ordem_id,
                    equipamento_id=eq_id,
                    produto_id=prod_id,
                    tipo_item=tipo_item,
                    quantidade=qtd,
                    valor_unitario=v_unit,
                    valor_total=v_total,
                    data_hora=make_dt_aware(row['DATA_HORA']),
                    data_hora_atualizada=make_dt_aware(row['DATA_HORA_ATUALIZADA']),
                    usuario=str(row['USUARIO'] or '').strip()[:50] or None,
                    usuario_atualizou=str(row['USUARIO_ATUALIZOU'] or '').strip()[:50] or None,
                )
                itens_instances.append(item_obj)

            if not dry_run:
                self.stdout.write(f'Gravando {len(itens_instances)} itens/peças de OS no PostgreSQL...')
                ItemOrdemServico.objects.bulk_create(itens_instances, batch_size=batch_size)

                # 4. Sincronizar sequências no PostgreSQL
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('ordem_servico_equipamentocliente', 'id'),
                            COALESCE((SELECT MAX(id) FROM ordem_servico_equipamentocliente), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('ordem_servico_ordemservico', 'id'),
                            COALESCE((SELECT MAX(id) FROM ordem_servico_ordemservico), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('ordem_servico_itemordemservico', 'id'),
                            COALESCE((SELECT MAX(id) FROM ordem_servico_itemordemservico), 1)
                        );
                    """)

        # Resumo final
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- ESTATÍSTICAS DA IMPORTAÇÃO DE ORDENS DE SERVIÇO ---'))
        self.stdout.write(f'  Equipamentos de Clientes      : {len(equipamentos_instances)}')
        self.stdout.write(f'  Ordens de Serviço Importadas  : {len(ordens_instances)}')
        self.stdout.write(f'    - Finalizadas               : {stats_status["FINALIZADO"]}')
        self.stdout.write(f'    - Orçamentos                : {stats_status["ORCAMENTO"]}')
        self.stdout.write(f'    - Aguardando                : {stats_status["AGUARDANDO"]}')
        self.stdout.write(f'  Peças e Serviços em OS        : {len(itens_instances)}')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n[DRY-RUN] Simulação concluída com sucesso! Nenhum dado foi inserido.'))
            return

        total_eq = EquipamentoCliente.objects.count()
        total_os = OrdemServico.objects.count()
        total_it = ItemOrdemServico.objects.count()
        self.stdout.write(self.style.SUCCESS('\nIMPORTAÇÃO DE ORDENS DE SERVIÇO CONCLUÍDA COM SUCESSO!'))
        self.stdout.write(self.style.SUCCESS(f'Total de equipamentos cadastrados: {total_eq}'))
        self.stdout.write(self.style.SUCCESS(f'Total de ordens de serviço no banco: {total_os}'))
        self.stdout.write(self.style.SUCCESS(f'Total de peças e serviços em OS   : {total_it}'))

