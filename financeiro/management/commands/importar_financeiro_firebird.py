import zoneinfo
from decimal import Decimal
from datetime import datetime, date
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
from vendas.models import Venda
from ordem_servico.models import OrdemServico
from financeiro.models import ContaBancaria, CategoriaFinanceira, TituloFinanceiro, BaixaTitulo


class Command(BaseCommand):
    help = 'Importa bancos e histórico financeiro (contas a pagar/receber e baixas) do Firebird (.FDB).'

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
            help='Remove registros existentes nas tabelas do app financeiro antes de importar.'
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

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO FINANCEIRA (FIREBIRD -> DJANGO) ==='))
        self.stdout.write(f'Arquivo: {caminho_arquivo}')
        self.stdout.write(f'Conexão: {host}:{porta} (Usuário: {usuario})')
        if dry_run:
            self.stdout.write(self.style.WARNING('[MODO DRY-RUN ATIVADO: Nenhuma alteração será salva no PostgreSQL]'))

        # Cache de dados de validação
        self.stdout.write('Carregando cadastro de Pessoas, Vendas e Ordens de Serviço do PostgreSQL...')
        pessoas_ids = set(Pessoas.objects.values_list('id', flat=True))
        vendas_ids = set(Venda.objects.values_list('id', flat=True))
        os_ids = set(OrdemServico.objects.values_list('id', flat=True))
        self.stdout.write(f'  Pessoas: {len(pessoas_ids)} | Vendas: {len(vendas_ids)} | OSs: {len(os_ids)}')

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

        # 1. Leitura de BANCOS
        self.stdout.write('Lendo tabela BANCOS do Firebird...')
        cur.execute("""
            SELECT
                CODIGO_BANCO,
                DESCRICAO_BANCO,
                AGENCIA
            FROM BANCOS
            ORDER BY CODIGO_BANCO
        """)
        bancos_fb = cur.fetchall()
        self.stdout.write(f'Total de bancos encontrados: {len(bancos_fb)}')

        # 2. Leitura de MOVIMENTOS
        self.stdout.write('Lendo tabela MOVIMENTOS do Firebird...')
        cur.execute("""
            SELECT
                CODIGO_MOVIMENTO,
                CODIGO_CLIENTE,
                PARCELA_MOVIMENTO,
                PLANO_PARCELA,
                REPARCELAMENTO,
                REFERENTE_A,
                DEBITO_CREDITO,
                QUITADO,
                DATA,
                DATA_VENCIMENTO,
                VALOR,
                VALOR_PAGO,
                VENDA_OU_ORDEM_OU_LANCAMENTO,
                CODIGO_VENDA_OU_ORDEM,
                USUARIO,
                USUARIO_ATUALIZOU,
                DATA_HORA,
                DATA_HORA_ATUALIZADA
            FROM MOVIMENTOS
            ORDER BY CODIGO_MOVIMENTO, PARCELA_MOVIMENTO, REPARCELAMENTO
        """)
        movimentos_fb = cur.fetchall()
        self.stdout.write(f'Total de movimentos encontrados no Firebird: {len(movimentos_fb)}')

        cur.close()
        conn.close()

        tz = zoneinfo.ZoneInfo(getattr(settings, 'TIME_ZONE', 'America/Sao_Paulo'))

        def parse_datetime(dt_val):
            if isinstance(dt_val, datetime):
                if timezone.is_naive(dt_val):
                    return timezone.make_aware(dt_val, tz)
                return dt_val
            return None

        # Categorias Padrão
        cat_venda, _ = CategoriaFinanceira.objects.get_or_create(nome='VENDAS DE MERCADORIAS', defaults={'tipo': 'RECEITA'})
        cat_os, _ = CategoriaFinanceira.objects.get_or_create(nome='SERVICOS E ASSISTENCIA TECNICA (OS)', defaults={'tipo': 'RECEITA'})
        cat_rec_outras, _ = CategoriaFinanceira.objects.get_or_create(nome='OUTRAS RECEITAS', defaults={'tipo': 'RECEITA'})
        cat_fornec, _ = CategoriaFinanceira.objects.get_or_create(nome='FORNECEDORES E COMPRAS', defaults={'tipo': 'DESPESA'})
        cat_desp_outras, _ = CategoriaFinanceira.objects.get_or_create(nome='OUTRAS DESPESAS OPERACIONAIS', defaults={'tipo': 'DESPESA'})

        # Mapear e preparar bancos
        bancos_instances = []
        for row in bancos_fb:
            cod_b, desc_b, ag_b = row
            b_obj = ContaBancaria(
                id=cod_b,
                descricao=str(desc_b).strip() if desc_b else f"BANCO {cod_b}",
                tipo_conta='CONTA_CORRENTE',
                banco_nome=str(desc_b).strip() if desc_b else None,
                agencia=str(ag_b).strip() if ag_b else None,
                saldo_inicial=Decimal('0.00'),
                ativo=True,
            )
            bancos_instances.append(b_obj)

        if not dry_run:
            for b in bancos_instances:
                ContaBancaria.objects.update_or_create(
                    id=b.id,
                    defaults={
                        'descricao': b.descricao,
                        'tipo_conta': b.tipo_conta,
                        'banco_nome': b.banco_nome,
                        'agencia': b.agencia,
                        'ativo': b.ativo,
                    }
                )

        caixa_balcao = ContaBancaria.objects.filter(tipo_conta='CAIXA_FISICO').first()
        if not caixa_balcao and not dry_run:
            caixa_balcao = ContaBancaria.objects.create(
                descricao='CAIXA FISICO / BALCAO',
                tipo_conta='CAIXA_FISICO',
                banco_nome='CAIXA INTERNO',
            )

        # Processar Movimentos -> TituloFinanceiro e BaixaTitulo
        titulos_instances = []
        baixas_instances = []

        total_receber = 0
        total_pagar = 0
        total_quitados = 0
        total_abertos = 0
        soma_valor_receber = Decimal('0.00')
        soma_valor_pagar = Decimal('0.00')

        # Usar sequência única para os IDs dos títulos
        seq_titulo_id = 1
        seq_baixa_id = 1

        for row in movimentos_fb:
            (
                cod_mov, cod_cli, parc_mov, plano_parc, reparc, ref_a,
                deb_cred, quitado, dt_mov, dt_venc, val_raw, val_pago_raw,
                tipo_origem, cod_origem, usr, usr_atu, dt_hr, dt_hr_atu
            ) = row

            if cod_cli not in pessoas_ids:
                continue

            tipo_titulo = 'RECEBER' if str(deb_cred).upper().strip() == 'D' else 'PAGAR'
            if tipo_titulo == 'RECEBER':
                total_receber += 1
            else:
                total_pagar += 1

            # Origem e vínculos
            origem = 'MANUAL'
            fk_venda_id = None
            fk_os_id = None
            cat_obj = cat_rec_outras if tipo_titulo == 'RECEBER' else cat_desp_outras

            orig_code = str(tipo_origem).upper().strip() if tipo_origem else 'L'
            if orig_code == 'V':
                origem = 'VENDA'
                cat_obj = cat_venda
                if cod_origem and cod_origem in vendas_ids:
                    fk_venda_id = cod_origem
            elif orig_code == 'O':
                origem = 'ORDEM_SERVICO'
                cat_obj = cat_os
                if cod_origem and cod_origem in os_ids:
                    fk_os_id = cod_origem
            elif orig_code == 'E':
                origem = 'COMPRA'
                cat_obj = cat_fornec

            # Datas
            d_emissao = dt_mov or dt_venc or date(2000, 1, 1)
            d_vencimento = dt_venc or dt_mov or date(2000, 1, 1)

            # Valores
            valor_orig = Decimal(str(val_raw)) if val_raw is not None else Decimal('0.00')
            if tipo_titulo == 'RECEBER':
                soma_valor_receber += valor_orig
            else:
                soma_valor_pagar += valor_orig

            is_quitado = (str(quitado).upper().strip() == 'S')
            if is_quitado:
                val_pago = Decimal(str(val_pago_raw)) if val_pago_raw is not None else valor_orig
                saldo = max(Decimal('0.00'), valor_orig - val_pago)
                status = 'PAGO' if saldo == Decimal('0.00') else 'PARCIAL'
                total_quitados += 1
            else:
                val_pago = Decimal('0.00')
                saldo = valor_orig
                status = 'ABERTO'
                total_abertos += 1

            # Descrição e documento
            desc = str(ref_a).strip() if ref_a and str(ref_a).strip() else f"Movimento #{cod_mov}"
            num_doc = f"{cod_mov}"

            # Auditoria
            dt_auditoria = parse_datetime(dt_hr) or timezone.now()
            dt_auditoria_atu = parse_datetime(dt_hr_atu) or dt_auditoria
            usr_clean = str(usr).strip() if usr else None
            usr_atu_clean = str(usr_atu).strip() if usr_atu else usr_clean

            titulo_id = seq_titulo_id
            seq_titulo_id += 1

            titulo_obj = TituloFinanceiro(
                id=titulo_id,
                tipo=tipo_titulo,
                pessoa_id=cod_cli,
                categoria=cat_obj,
                origem=origem,
                venda_id=fk_venda_id,
                ordem_servico_id=fk_os_id,
                numero_documento=num_doc,
                parcela_numero=int(parc_mov) if parc_mov is not None else 1,
                parcela_total=int(plano_parc) if plano_parc is not None else 1,
                descricao=desc,
                data_emissao=d_emissao,
                data_vencimento=d_vencimento,
                valor_original=valor_orig,
                valor_pago=val_pago,
                saldo_devedor=saldo,
                status=status,
                forma_pagamento_prevista=None,
                observacoes=f"Registro Firebird: Movimento {cod_mov}, Parcela {parc_mov}/{plano_parc}, Reparc {reparc}",
                usuario=usr_clean,
                usuario_atualizou=usr_atu_clean,
                data_hora=dt_auditoria,
                data_hora_atualizada=dt_auditoria_atu,
            )
            titulos_instances.append(titulo_obj)

            # Se estiver quitado ou com valor pago > 0, cria o registro na tabela de Baixas
            if is_quitado and val_pago != Decimal('0.00'):
                baixa_id = seq_baixa_id
                seq_baixa_id += 1

                baixa_obj = BaixaTitulo(
                    id=baixa_id,
                    titulo_id=titulo_id,
                    conta_bancaria=caixa_balcao,
                    data_pagamento=d_vencimento,
                    valor_pago=val_pago,
                    juros_multa=Decimal('0.00'),
                    desconto=Decimal('0.00'),
                    forma_pagamento='DINHEIRO',
                    identificador_transacao=f"FB-MOV-{cod_mov}",
                    observacoes="Baixa histórica importada do Firebird",
                    usuario=usr_clean,
                    usuario_atualizou=usr_atu_clean,
                    data_hora=dt_auditoria,
                    data_hora_atualizada=dt_auditoria_atu,
                )
                baixas_instances.append(baixa_obj)

        with transaction.atomic():
            if limpar and not dry_run:
                self.stdout.write(self.style.WARNING('Limpando registros existentes no app financeiro...'))
                BaixaTitulo.objects.all().delete()
                TituloFinanceiro.objects.all().delete()

            if not dry_run:
                # 1. Salvar Títulos
                self.stdout.write(f'Gravando {len(titulos_instances)} títulos financeiros no PostgreSQL...')
                TituloFinanceiro.objects.bulk_create(titulos_instances, batch_size=batch_size)

                # 2. Salvar Baixas
                self.stdout.write(f'Gravando {len(baixas_instances)} baixas de títulos no PostgreSQL...')
                BaixaTitulo.objects.bulk_create(baixas_instances, batch_size=batch_size)

                # 4. Sincronizar sequências no PostgreSQL
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('financeiro_titulofinanceiro', 'id'),
                            COALESCE((SELECT MAX(id) FROM financeiro_titulofinanceiro), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('financeiro_baixatitulo', 'id'),
                            COALESCE((SELECT MAX(id) FROM financeiro_baixatitulo), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('financeiro_contabancaria', 'id'),
                            COALESCE((SELECT MAX(id) FROM financeiro_contabancaria), 1)
                        );
                    """)
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('financeiro_categoriafinanceira', 'id'),
                            COALESCE((SELECT MAX(id) FROM financeiro_categoriafinanceira), 1)
                        );
                    """)

        # Resumo final
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- ESTATÍSTICAS DA IMPORTAÇÃO FINANCEIRA ---'))
        self.stdout.write(f'  Bancos cadastrados            : {len(bancos_instances)}')
        self.stdout.write(f'  Títulos Importados            : {len(titulos_instances)}')
        self.stdout.write(f'    - Contas a Receber          : {total_receber} (Total: R$ {soma_valor_receber:,.2f})')
        self.stdout.write(f'    - Contas a Pagar            : {total_pagar} (Total: R$ {soma_valor_pagar:,.2f})')
        self.stdout.write(f'    - Quitados / Parciais       : {total_quitados}')
        self.stdout.write(f'    - Em Aberto                 : {total_abertos}')
        self.stdout.write(f'  Baixas / Pagamentos Criados   : {len(baixas_instances)}')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n[DRY-RUN] Simulação concluída com sucesso! Nenhum dado foi inserido.'))
            return

        total_t = TituloFinanceiro.objects.count()
        total_b = BaixaTitulo.objects.count()
        self.stdout.write(self.style.SUCCESS('\nIMPORTAÇÃO FINANCEIRA CONCLUÍDA COM SUCESSO!'))
        self.stdout.write(self.style.SUCCESS(f'Total de títulos financeiros no banco: {total_t}'))
        self.stdout.write(self.style.SUCCESS(f'Total de baixas registradas no banco  : {total_b}'))
