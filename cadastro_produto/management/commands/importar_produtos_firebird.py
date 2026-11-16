import re
import zoneinfo
from decimal import Decimal
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

from cadastro_produto.models import Produtos, Categoria, Marca, UnidadeMedida
from fiscal.models import Ncm, Cfop


class Command(BaseCommand):
    help = 'Importa produtos, categorias, marcas, unidades de medida e dados fiscais do Firebird (.FDB) para o app cadastro_produto.'

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
            default=500,
            help='Tamanho do lote para inserção no PostgreSQL (padrão: 500).'
        )
        parser.add_argument(
            '--limpar',
            action='store_true',
            help='Remove os produtos existentes na tabela cadastro_produto_produtos antes de iniciar.'
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

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO DE PRODUTOS E CATÁLOGO (FIREBIRD -> DJANGO) ==='))
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

        # 1. Carregar Categorias (TIPO_PRODUTO)
        self.stdout.write('Carregando categorias (TIPO_PRODUTO)...')
        cur.execute('SELECT CODIGO_TIPO_PRODUTO, DESCRICAO_TIPO_PRODUTO FROM TIPO_PRODUTO')
        fb_tipos = cur.fetchall()

        # 2. Carregar Marcas (MARCA_PRODUTO)
        self.stdout.write('Carregando marcas (MARCA_PRODUTO)...')
        cur.execute('SELECT CODIGO_MARCA_PRODUTO, DESCRICAO_MARCA_PRODUTO FROM MARCA_PRODUTO')
        fb_marcas = cur.fetchall()

        # 3. Carregar Unidades de Medida
        self.stdout.write('Carregando unidades de medida...')
        cur.execute('SELECT CODIGO_UNIDADE_MEDIDA, DESCRICAO_CODIGO_MEDIDA, DESCRICAO_ABREVIADA FROM UNIDADES_MEDIDA')
        fb_unidades = cur.fetchall()

        # 4. Carregar CFOPs
        self.stdout.write('Carregando tabela oficial de CFOPs do legado...')
        cur.execute('SELECT CFOP, DESCRICAO FROM CFOP')
        fb_cfops = cur.fetchall()

        # 5. Carregar Produtos
        self.stdout.write('Carregando produtos (PRODUTOS)...')
        cur.execute("""
            SELECT 
                CODIGO_PRODUTO, CODIGO_BARRA_PRODUTO, CODIGO_NET_PRODUTO,
                DESCRICAO_PRODUTO, CODIGO_TIPO_PRODUTO, CODIGO_MARCA_PRODUTO,
                CODIGO_UNIDADE_MEDIDA, CUSTO, VALOR_FINAL, VALOR_AVISTA,
                QUANTIDADE, QUANTIDADE_MINIMA, LUCRO, LUCRO_PORC_CUSTO,
                OBS, ATIVO, CONTROLA_NSERIE, CLASS_FISCAL_NCM, CFOP,
                PART_NUMBER, USUARIO, USUARIO_ATUALIZOU, DATA_HORA, DATA_HORA_ATUALIZADA
            FROM PRODUTOS
            ORDER BY CODIGO_PRODUTO
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        total_rows = len(rows)
        self.stdout.write(f'Total de produtos encontrados no Firebird: {total_rows}')

        conn.close()

        tz = timezone.get_current_timezone()

        stats = {
            'total': total_rows,
            'ativo_sim': 0,
            'ativo_nao': 0,
            'barcodes_valid': 0,
            'barcodes_internal': 0,
            'barcodes_gs1_fixed': 0,
            'barcodes_serial_part': 0,
            'negative_stock_handled': 0,
            'ncm_matched': 0,
            'cfop_matched': 0,
            'categorias_mapped': 0,
            'marcas_mapped': 0,
            'unidades_mapped': 0,
        }

        with transaction.atomic():
            if limpar and not dry_run:
                self.stdout.write(self.style.WARNING('Limpando tabela cadastro_produto_produtos...'))
                Produtos.objects.all().delete()

            # 1. Sincronizar Categorias
            cat_map = {}
            for t_id, t_nome in fb_tipos:
                nome_clean = unidecode(str(t_nome or '')).upper().strip()
                if not nome_clean or nome_clean == 'PADRAO - TIPO AINDA NAO CADASTRADO':
                    nome_clean = 'DIVERSOS / NAO CADASTRADO'
                if dry_run:
                    cat_obj = Categoria.objects.filter(nome=nome_clean[:80]).first()
                    if not cat_obj:
                        cat_obj = Categoria(id=t_id, nome=nome_clean[:80])
                else:
                    cat_obj, _ = Categoria.objects.get_or_create(nome=nome_clean[:80])
                cat_map[t_id] = cat_obj

            # 2. Sincronizar Marcas
            marca_map = {}
            for m_id, m_nome in fb_marcas:
                nome_clean = unidecode(str(m_nome or '')).upper().strip()
                if not nome_clean or nome_clean == 'PADRAO - MARCA AINDA NAO CADASTRADO':
                    nome_clean = 'GENERICO / NAO CADASTRADO'
                if dry_run:
                    marca_obj = Marca.objects.filter(nome=nome_clean[:80]).first()
                    if not marca_obj:
                        marca_obj = Marca(id=m_id, nome=nome_clean[:80])
                else:
                    marca_obj, _ = Marca.objects.get_or_create(nome=nome_clean[:80])
                marca_map[m_id] = marca_obj

            # 3. Sincronizar Unidades de Medida
            unidade_un = UnidadeMedida.objects.filter(sigla='UN').first()
            unidade_pc = UnidadeMedida.objects.filter(sigla='PC').first() or unidade_un
            unidade_mt = UnidadeMedida.objects.filter(sigla='MT').first() or unidade_un

            if dry_run:
                unidade_cj = UnidadeMedida.objects.filter(sigla='CJ').first() or unidade_un
                unidade_sv = UnidadeMedida.objects.filter(sigla='SV').first() or unidade_un
            else:
                unidade_cj, _ = UnidadeMedida.objects.get_or_create(sigla='CJ', defaults={'descricao': 'CONJUNTO'})
                unidade_sv, _ = UnidadeMedida.objects.get_or_create(sigla='SV', defaults={'descricao': 'SERVICO'})

            unidade_map = {
                1: unidade_pc,  # PEÇAS
                2: unidade_mt,  # METROS
                3: unidade_cj,  # CONJUNTO
                4: unidade_sv,  # SERVIÇOS
                5: unidade_un,  # NÃO CADAS
            }

            # 4. Sincronizar CFOPs
            cfop_map = {}
            for c_cod, c_desc in fb_cfops:
                cod_str = re.sub(r'\D', '', str(c_cod or ''))
                if len(cod_str) == 4:
                    tipo_op = 'ENTRADA' if cod_str[0] in ('1', '2', '3') else 'SAIDA'
                    if dry_run:
                        cfop_obj = Cfop.objects.filter(codigo=cod_str).first()
                        if not cfop_obj:
                            cfop_obj = Cfop(codigo=cod_str, descricao=unidecode(str(c_desc or ''))[:255], tipo_operacao=tipo_op)
                    else:
                        cfop_obj, _ = Cfop.objects.get_or_create(
                            codigo=cod_str,
                            defaults={
                                'descricao': unidecode(str(c_desc or ''))[:255],
                                'tipo_operacao': tipo_op,
                                'movimenta_estoque': True,
                                'ativo': True
                            }
                        )
                    cfop_map[cod_str] = cfop_obj

            # 5. Sincronizar NCMs
            ncm_map = {}
            for r in rows:
                raw_ncm = str(r[17] or '').strip()
                if raw_ncm:
                    digits = re.sub(r'\D', '', raw_ncm)
                    if len(digits) in (7, 8):
                        digits_padded = digits.zfill(8)
                        if digits_padded not in ncm_map:
                            if dry_run:
                                ncm_obj = Ncm.objects.filter(codigo=digits_padded).first()
                                if not ncm_obj:
                                    ncm_obj = Ncm(codigo=digits_padded, descricao=f'NCM {digits_padded}', ativo=True)
                            else:
                                ncm_obj, _ = Ncm.objects.get_or_create(
                                    codigo=digits_padded,
                                    defaults={
                                        'descricao': f'NCM {digits_padded}',
                                        'ativo': True
                                    }
                                )
                            ncm_map[digits_padded] = ncm_obj
                            ncm_map[digits] = ncm_obj

            # 6. Preparar instâncias de Produtos
            produtos_instances = []

            for r in rows:
                row = dict(zip(cols, r))
                cod_prod = row['CODIGO_PRODUTO']
                nome = unidecode(str(row['DESCRICAO_PRODUTO'] or '')).upper().strip()[:150]
                if not nome:
                    nome = f'PRODUTO #{cod_prod}'

                # Ativo
                is_ativo = str(row['ATIVO'] or '').strip().upper() == 'S'
                if is_ativo:
                    stats['ativo_sim'] += 1
                else:
                    stats['ativo_nao'] += 1

                # Controla Número de Série
                ctrl_ns_raw = str(row['CONTROLA_NSERIE'] or '').strip().upper()
                controla_ns = ctrl_ns_raw in ('S', 'SIM')

                # Barcode / SKU
                raw_bc = str(row['CODIGO_BARRA_PRODUTO'] or '').strip()
                part_num = unidecode(str(row['PART_NUMBER'] or '')).upper().strip()[:60] if row['PART_NUMBER'] else None
                codigo_barras = None
                codigo_interno = f'PROD-{cod_prod}'

                notes = []
                raw_obs = str(row['OBS'] or '').strip()
                if raw_obs:
                    notes.append(raw_obs)

                if raw_bc:
                    if raw_bc.isdigit() and len(raw_bc) in (8, 12, 13, 14):
                        codigo_barras = raw_bc
                        stats['barcodes_valid'] += 1
                    elif raw_bc.isdigit() and len(raw_bc) == 16 and raw_bc.startswith('01'):
                        codigo_barras = raw_bc[2:]  # Remove prefixo AI 01 do GS1
                        stats['barcodes_gs1_fixed'] += 1
                    elif len(raw_bc) <= 6:
                        codigo_barras = None
                        stats['barcodes_internal'] += 1
                    else:
                        notes.append(f'[Codigo Barras legado: {raw_bc}]')
                        stats['barcodes_serial_part'] += 1
                        if not part_num and len(raw_bc) <= 60:
                            part_num = raw_bc

                # Estoque Atual e Mínimo
                raw_qtd = row['QUANTIDADE']
                if raw_qtd is not None:
                    qtd_int = int(Decimal(str(raw_qtd)))
                    if qtd_int < 0:
                        stats['negative_stock_handled'] += 1
                        notes.append(f'[Saldo legado negativo: {qtd_int}]')
                        estoque_atual = 0
                    else:
                        estoque_atual = qtd_int
                else:
                    estoque_atual = 0

                raw_min = row['QUANTIDADE_MINIMA']
                estoque_min = int(Decimal(str(raw_min))) if raw_min is not None and Decimal(str(raw_min)) > 0 else 0

                # Preços e Margem
                raw_custo = row['CUSTO']
                preco_custo = Decimal(str(raw_custo)).quantize(Decimal('0.01')) if raw_custo and Decimal(str(raw_custo)) > 0 else Decimal('0.00')

                raw_venda = row['VALOR_FINAL'] or row['VALOR_AVISTA']
                preco_venda = Decimal(str(raw_venda)).quantize(Decimal('0.01')) if raw_venda and Decimal(str(raw_venda)) > 0 else Decimal('0.00')

                raw_avista = row['VALOR_AVISTA']
                if raw_avista and raw_venda and Decimal(str(raw_avista)) < Decimal(str(raw_venda)) and Decimal(str(raw_avista)) > 0:
                    preco_promocional = Decimal(str(raw_avista)).quantize(Decimal('0.01'))
                else:
                    preco_promocional = None

                raw_lucro = row['LUCRO_PORC_CUSTO'] or row['LUCRO']
                if raw_lucro and Decimal(str(raw_lucro)) > 0:
                    margem_lucro = Decimal(str(raw_lucro)).quantize(Decimal('0.01'))
                elif preco_custo > 0 and preco_venda > 0:
                    margem_lucro = (((preco_venda - preco_custo) / preco_custo) * 100).quantize(Decimal('0.01'))
                else:
                    margem_lucro = None

                # Chaves Estrangeiras
                cat_obj = cat_map.get(row['CODIGO_TIPO_PRODUTO'])
                if cat_obj:
                    stats['categorias_mapped'] += 1

                marca_obj = marca_map.get(row['CODIGO_MARCA_PRODUTO'])
                if marca_obj:
                    stats['marcas_mapped'] += 1

                unidade_obj = unidade_map.get(row['CODIGO_UNIDADE_MEDIDA'], unidade_un)
                if unidade_obj:
                    stats['unidades_mapped'] += 1

                # NCM e CFOP
                ncm_obj = None
                raw_ncm = str(row['CLASS_FISCAL_NCM'] or '').strip()
                if raw_ncm:
                    d_ncm = re.sub(r'\D', '', raw_ncm)
                    ncm_obj = ncm_map.get(d_ncm.zfill(8))
                    if ncm_obj:
                        stats['ncm_matched'] += 1

                cfop_obj = None
                raw_cfop = str(row['CFOP'] or '').strip()
                if raw_cfop:
                    d_cfop = re.sub(r'\D', '', raw_cfop)
                    cfop_obj = cfop_map.get(d_cfop)
                    if cfop_obj:
                        stats['cfop_matched'] += 1

                # Auditoria e Timestamps
                def make_dt_aware(dt_val):
                    if not dt_val:
                        return None
                    if timezone.is_naive(dt_val):
                        try:
                            return timezone.make_aware(dt_val, tz)
                        except Exception:
                            return dt_val.replace(tzinfo=zoneinfo.ZoneInfo('America/Sao_Paulo'))
                    return dt_val

                data_hora = make_dt_aware(row['DATA_HORA'])
                data_hora_atualizada = make_dt_aware(row['DATA_HORA_ATUALIZADA'])

                usuario = str(row['USUARIO'] or '').strip()[:50] or None
                usuario_atualizou = str(row['USUARIO_ATUALIZOU'] or '').strip()[:50] or None

                obs_final = '\n'.join(notes).strip() or None

                p = Produtos(
                    id=cod_prod,
                    codigo_interno=codigo_interno,
                    codigo_barras=codigo_barras,
                    nome=nome,
                    marca=marca_obj,
                    part_number=part_num,
                    categoria=cat_obj,
                    unidade_medida=unidade_obj,
                    condicao='NOVO',
                    preco_custo=preco_custo,
                    preco_venda=preco_venda,
                    preco_promocional=preco_promocional,
                    margem_lucro=margem_lucro,
                    estoque_atual=estoque_atual,
                    estoque_minimo=estoque_min,
                    controla_numero_serie=controla_ns,
                    ncm=ncm_obj,
                    cfop=cfop_obj,
                    ativo=is_ativo,
                    obs=obs_final,
                    usuario=usuario,
                    usuario_atualizou=usuario_atualizou,
                    data_hora=data_hora,
                    data_hora_atualizada=data_hora_atualizada,
                )
                produtos_instances.append(p)

            # Resumo
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- ESTATÍSTICAS DA IMPORTAÇÃO DE PRODUTOS ---'))
            self.stdout.write(f'  Total de produtos processados : {stats["total"]}')
            self.stdout.write(f'    - Ativos                    : {stats["ativo_sim"]}')
            self.stdout.write(f'    - Inativos                  : {stats["ativo_nao"]}')
            self.stdout.write(f'  Códigos de barras válidos/EAN : {stats["barcodes_valid"]}')
            self.stdout.write(f'  Códigos internos (SKU legado) : {stats["barcodes_internal"]}')
            self.stdout.write(f'  Códigos GS1 corrigidos (AI 01): {stats["barcodes_gs1_fixed"]}')
            self.stdout.write(f'  Códigos seriais/PN anotados   : {stats["barcodes_serial_part"]}')
            self.stdout.write(f'  Saldos negativos ajustados    : {stats["negative_stock_handled"]}')
            self.stdout.write(f'  Categorias mapeadas (100%)    : {stats["categorias_mapped"]} / {stats["total"]}')
            self.stdout.write(f'  Marcas mapeadas (100%)        : {stats["marcas_mapped"]} / {stats["total"]}')
            self.stdout.write(f'  Unidades de medida (100%)     : {stats["unidades_mapped"]} / {stats["total"]}')
            self.stdout.write(f'  NCMs tributários associados   : {stats["ncm_matched"]} / {stats["total"]}')
            self.stdout.write(f'  CFOPs padrão associados       : {stats["cfop_matched"]} / {stats["total"]}')

            if dry_run:
                self.stdout.write(self.style.SUCCESS('\n[DRY-RUN] Simulação concluída com sucesso! Nenhum dado foi inserido.'))
                transaction.set_rollback(True)
                return

            self.stdout.write('\nGravando produtos no PostgreSQL...')
            Produtos.objects.bulk_create(
                produtos_instances,
                batch_size=batch_size,
                ignore_conflicts=False
            )

            # Atualizar sequência do PostgreSQL
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT setval(
                        pg_get_serial_sequence('cadastro_produto_produtos', 'id'),
                        COALESCE((SELECT MAX(id) FROM cadastro_produto_produtos), 1)
                    );
                """)

        total_final = Produtos.objects.count()
        total_categorias = Categoria.objects.count()
        total_marcas = Marca.objects.count()
        self.stdout.write(self.style.SUCCESS('\nIMPORTAÇÃO DE PRODUTOS CONCLUÍDA COM SUCESSO!'))
        self.stdout.write(self.style.SUCCESS(f'Total de produtos no banco  : {total_final}'))
        self.stdout.write(self.style.SUCCESS(f'Total de categorias no banco: {total_categorias}'))
        self.stdout.write(self.style.SUCCESS(f'Total de marcas no banco    : {total_marcas}'))

