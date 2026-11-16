import re
import zoneinfo
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

from cadastro.models import Pessoas, Cidade
from cadastro.validators import (
    apenas_digitos,
    formatar_cpf_cnpj,
    formatar_cep,
    formatar_telefone,
    validar_digitos_cpf,
    validar_digitos_cnpj,
)


CITY_ALIASES = {
    ('OSWALDO CRUZ', 'SP'): ('OSVALDO CRUZ', 'SP'),
    ('MIRASOL', 'SP'): ('MIRASSOL', 'SP'),
    ('NOVO AMBURGO', 'RS'): ('NOVO HAMBURGO', 'RS'),
    ('MOGI IGUAÇU', 'SP'): ('MOGI GUACU', 'SP'),
    ('MOGI IGUACU', 'SP'): ('MOGI GUACU', 'SP'),
    ('MURITINGA DO SUL', 'SP'): ('MURUTINGA DO SUL', 'SP'),
    ("BIRIGUI '", 'SP'): ('BIRIGUI', 'SP'),
    ('PORTO TROMBETAS', 'PA'): ('ORIXIMINA', 'PA'),
    ('JURITIS', 'SP'): ('GLICERIO', 'SP'),
    ('RIO DE JANEIRO', 'SP'): ('RIO DE JANEIRO', 'RJ'),
}

EMAIL_REGEX = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', re.IGNORECASE)
ADDRESS_SPLIT_REGEX = re.compile(r'^(.*?)[,\s]+(?:N[º°.]?\s*)?(\d+[A-Za-z]?|S/?N)(?:[,\s;\-]+(.*))?$', re.I)


class Command(BaseCommand):
    help = 'Importa fornecedores (CODIGO_TIPO_PESSOA = 2) e funcionários/técnicos (CODIGO_TIPO_PESSOA = 3) do Firebird (.FDB) para o Django.'

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
            '--apenas-fornecedores',
            action='store_true',
            help='Importa apenas Fornecedores (tipo 2), ignorando Funcionários/Técnicos (tipo 3).'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Tamanho do lote para inserção no PostgreSQL (padrão: 500).'
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
        apenas_fornecedores = options['apenas_fornecedores']
        batch_size = options['batch_size']
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO DE FORNECEDORES E FUNCIONÁRIOS (FIREBIRD -> DJANGO) ==='))
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

        # 1. Mapeamento de cidades
        self.stdout.write('Mapeando cidades do legado...')
        cur.execute('SELECT CODIGO_CIDADE, DESCRICAO_CIDADE, UF_CIDADE, CODIGO_IBGE FROM CIDADES')
        fb_cidades = cur.fetchall()

        cidade_map = {}
        for cid_id, nome, uf, ibge in fb_cidades:
            nome_str = nome.strip() if nome else ''
            uf_str = uf.strip() if uf else ''
            ibge_str = ibge.strip() if ibge else ''

            c = None
            if ibge_str:
                c = Cidade.objects.filter(codigoIbge=ibge_str).first()
            if not c and nome_str and uf_str:
                c = Cidade.objects.filter(descricaoCidade__iexact=nome_str, uf__uf=uf_str).first()
            if not c and nome_str and uf_str:
                c = Cidade.objects.filter(descricaoCidade__iexact=unidecode(nome_str).upper(), uf__uf=uf_str).first()
            if not c and (nome_str, uf_str) in CITY_ALIASES:
                alias_nome, alias_uf = CITY_ALIASES[(nome_str, uf_str)]
                c = Cidade.objects.filter(descricaoCidade__iexact=unidecode(alias_nome).upper(), uf__uf=alias_uf).first()

            cidade_map[cid_id] = c

        total_cidades_mapeadas = sum(1 for v in cidade_map.values() if v is not None)
        self.stdout.write(f'Cidades no Firebird: {len(fb_cidades)} | Mapeadas no Django: {total_cidades_mapeadas}')

        # 2. Consultar Fornecedores e Funcionários
        tipos = (2,) if apenas_fornecedores else (2, 3)
        tipos_str = ', '.join(str(t) for t in tipos)

        cur.execute(f"""
            SELECT 
                CODIGO_PESSOA, CODIGO_TIPO_PESSOA, RAZAO_NOME, FANTASIA_APELIDO,
                ENDERECO_PESSOA, BAIRRO_PESSOA, CEP_PESSOA, CAIXA_POSTAL,
                INSCRICAO_RG, CNPJ_CFP, DT_NASC_FUND, PRIMEIRA_COMPRA, ULTIMA_COMPRA,
                CODIGO_CIDADE, TIPO_JURIDICA_FISICA, TEL, TELCOMERCIAL, CELULAR,
                EMAIL, OBS, USUARIO, USUARIO_ATUALIZOU, DATA_HORA, DATA_HORA_ATUALIZADA,
                ATIVO, NUMERO, COMPLEMENTO_END
            FROM PESSOAS 
            WHERE CODIGO_TIPO_PESSOA IN ({tipos_str})
            ORDER BY CODIGO_PESSOA
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        total_rows = len(rows)
        self.stdout.write(f'Total de registros a importar: {total_rows}')

        tz = timezone.get_current_timezone()

        # Documentos já existentes no banco para evitar violações de unicidade
        seen_documents = {}
        for p in Pessoas.objects.exclude(cnpj_cpf__isnull=True).values('id', 'cnpj_cpf'):
            digits = apenas_digitos(p['cnpj_cpf'])
            if digits:
                seen_documents[digits] = p['id']

        reassign_doc_pks = {}  # pk -> digits para reatribuição legítima (ex: ID 508 -> ID 346)

        stats = {
            'total': total_rows,
            'fornecedores': sum(1 for r in rows if r[1] == 2),
            'funcionarios': sum(1 for r in rows if r[1] == 3),
            'valid_cpf': 0,
            'valid_cnpj': 0,
            'doc_empty': 0,
            'doc_incomplete': 0,
            'doc_duplicates': 0,
            'cities_matched': 0,
            'cities_unmatched': 0,
            'address_numbers_extracted': 0,
            'emails_extracted': 0,
            'emails_notes': 0,
            'inactive_flagged': 0,
        }

        pessoas_instances = []

        for r in rows:
            row = dict(zip(cols, r))
            codigo = row['CODIGO_PESSOA']
            tipo_fb = row['CODIGO_TIPO_PESSOA']

            # Mapeamento do tipo de pessoa e funcionário:
            # Tipo 2 (FORNECEDOR) -> tipo_pessoa = 1, funcionario = False
            # Tipo 3 (FUNCIONARIO/TECNICO) -> tipo_pessoa = 0 (CLIENTE), funcionario = True
            if tipo_fb == 2:
                tipo_pessoa = 1
                funcionario = False
            else:
                tipo_pessoa = 0
                funcionario = True

            razao = unidecode(str(row['RAZAO_NOME'] or '')).upper().strip()[:100]
            if not razao:
                razao = f'FORNECEDOR #{codigo}' if tipo_fb == 2 else f'FUNCIONARIO #{codigo}'

            fantasia = unidecode(str(row['FANTASIA_APELIDO'] or '')).upper().strip()[:100] if row['FANTASIA_APELIDO'] else None

            notes = []
            raw_obs = str(row['OBS'] or '').strip()
            if raw_obs:
                notes.append(raw_obs)

            if str(row['ATIVO'] or '').strip().upper() == 'F':
                notes.append('[REGISTRO INATIVO NO SISTEMA ANTERIOR]')
                stats['inactive_flagged'] += 1

            raw_doc = str(row['CNPJ_CFP'] or '').strip()
            doc_digits = apenas_digitos(raw_doc)

            cnpj_cpf = None
            juridica_fisica = 0 if str(row['TIPO_JURIDICA_FISICA'] or '').strip().upper() == 'J' else 1

            if not doc_digits:
                stats['doc_empty'] += 1
            elif len(doc_digits) == 11:
                juridica_fisica = 1  # 11 dígitos = Física
                if validar_digitos_cpf(doc_digits):
                    stats['valid_cpf'] += 1
                else:
                    notes.append(f'[AVISO: CPF com digito verificador inconsistente no legado: {raw_doc}]')

                # Tratamento do CPF do proprietário Edson Heiji Kato Junior (ID 346)
                if doc_digits == '28264488897' and codigo == 346:
                    orig_id = seen_documents.get(doc_digits)
                    if orig_id and orig_id != 346:
                        reassign_doc_pks[orig_id] = doc_digits
                    cnpj_cpf = formatar_cpf_cnpj(doc_digits)
                    seen_documents[doc_digits] = 346
                elif doc_digits in seen_documents:
                    stats['doc_duplicates'] += 1
                    orig_id = seen_documents[doc_digits]
                    notes.append(f'[DOC DUPLICADO: {formatar_cpf_cnpj(doc_digits)} - Cadastro mantido no ID {orig_id}]')
                    cnpj_cpf = None
                else:
                    seen_documents[doc_digits] = codigo
                    cnpj_cpf = formatar_cpf_cnpj(doc_digits)
            elif len(doc_digits) == 14:
                juridica_fisica = 0  # 14 dígitos = Jurídica
                if validar_digitos_cnpj(doc_digits):
                    stats['valid_cnpj'] += 1
                else:
                    notes.append(f'[AVISO: CNPJ com digito verificador inconsistente no legado: {raw_doc}]')

                if doc_digits in seen_documents:
                    stats['doc_duplicates'] += 1
                    orig_id = seen_documents[doc_digits]
                    notes.append(f'[DOC DUPLICADO: {formatar_cpf_cnpj(doc_digits)} - Cadastro mantido no ID {orig_id}]')
                    cnpj_cpf = None
                else:
                    seen_documents[doc_digits] = codigo
                    cnpj_cpf = formatar_cpf_cnpj(doc_digits)
            else:
                stats['doc_incomplete'] += 1
                notes.append(f'[DOC INCOMPLETO NO LEGADO: {raw_doc}]')
                cnpj_cpf = None

            # Endereço e Número
            raw_end = str(row['ENDERECO_PESSOA'] or '').strip()
            raw_num = str(row['NUMERO'] or '').strip()
            raw_comp = str(row['COMPLEMENTO_END'] or '').strip()

            endereco = None
            numero = None
            complemento = unidecode(raw_comp).upper()[:50] if raw_comp else None

            if raw_num:
                numero = unidecode(raw_num).upper()[:18]
                endereco = unidecode(raw_end).upper()[:100] if raw_end else None
            elif raw_end:
                m = ADDRESS_SPLIT_REGEX.match(raw_end)
                if m:
                    logr = m.group(1).rstrip(', ').strip()
                    num = m.group(2).strip()
                    comp = m.group(3).strip() if m.group(3) else None

                    endereco = unidecode(logr).upper()[:100]
                    numero = unidecode(num).upper()[:18]
                    stats['address_numbers_extracted'] += 1
                    if comp:
                        comp_clean = unidecode(comp).upper()
                        if complemento:
                            complemento = f'{complemento} / {comp_clean}'[:50]
                        else:
                            complemento = comp_clean[:50]
                else:
                    endereco = unidecode(raw_end.rstrip(', ')).upper()[:100]

            raw_bairro = str(row['BAIRRO_PESSOA'] or '').strip()
            bairro = unidecode(raw_bairro).upper()[:50] if raw_bairro else None

            raw_cep = str(row['CEP_PESSOA'] or '').strip()
            cep_digits = apenas_digitos(raw_cep)
            cep = None
            if len(cep_digits) == 8 and len(set(cep_digits)) > 1:
                cep = f'{cep_digits[:5]}-{cep_digits[5:]}'
            elif cep_digits:
                notes.append(f'[CEP INVALIDO NO LEGADO: {raw_cep}]')

            codigo_cidade_fb = row['CODIGO_CIDADE']
            cidade_obj = cidade_map.get(codigo_cidade_fb)
            if cidade_obj:
                stats['cities_matched'] += 1
            else:
                stats['cities_unmatched'] += 1

            def format_phone_field(raw_phone):
                if not raw_phone:
                    return None
                digits = apenas_digitos(raw_phone)
                if len(digits) in (10, 11):
                    return formatar_telefone(digits)
                elif len(digits) == 8:
                    return f'{digits[:4]}-{digits[4:]}'
                elif len(digits) == 9:
                    return f'{digits[:5]}-{digits[5:]}'
                return None

            telefone = format_phone_field(row['TEL'])
            telefone2 = format_phone_field(row['TELCOMERCIAL'])
            celular = format_phone_field(row['CELULAR'])

            raw_email = str(row['EMAIL'] or '').strip()
            email = None
            if raw_email:
                em_match = EMAIL_REGEX.search(raw_email)
                if em_match:
                    email = em_match.group(1).lower()[:100]
                    stats['emails_extracted'] += 1
                    trailing = raw_email.replace(em_match.group(1), '').strip()
                    if trailing and any(c.isalnum() for c in trailing):
                        notes.append(f'[Nota Contato/Email: {trailing}]')
                        stats['emails_notes'] += 1
                else:
                    if any(c.isalnum() for c in raw_email):
                        notes.append(f'[Info Contato: {raw_email}]')
                        stats['emails_notes'] += 1

            raw_rg = str(row['INSCRICAO_RG'] or '').strip()
            inscricao_rg = unidecode(raw_rg).upper()[:15] if raw_rg else None

            raw_cp = str(row['CAIXA_POSTAL'] or '').strip()
            caixa_postal = raw_cp[:18] if raw_cp and raw_cp != '0' else None

            def fix_date(d):
                if not d:
                    return None
                if d.year < 1000:
                    return d.replace(year=d.year + 1000)
                return d

            dt_nasc_fund = fix_date(row['DT_NASC_FUND'])
            primeira_compra = fix_date(row['PRIMEIRA_COMPRA'])
            ultima_compra = fix_date(row['ULTIMA_COMPRA'])

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

            p = Pessoas(
                id=codigo,
                tipo_pessoa=tipo_pessoa,
                funcionario=funcionario,
                juridica_fisica=juridica_fisica,
                razao_nome=razao,
                fantasia_contato=fantasia,
                cnpj_cpf=cnpj_cpf,
                inscricao_rg=inscricao_rg,
                endereco=endereco,
                numero=numero,
                complemento=complemento,
                bairro=bairro,
                cep=cep,
                codigo_cidade=cidade_obj,
                caixa_postal=caixa_postal,
                celular=celular,
                telefone=telefone,
                telefone2=telefone2,
                dt_nasc_fund=dt_nasc_fund,
                primeira_compra=primeira_compra,
                ultima_compra=ultima_compra,
                email=email,
                obs=obs_final,
                usuario=usuario,
                usuario_atualizou=usuario_atualizou,
                data_hora=data_hora,
                data_hora_atualizada=data_hora_atualizada,
            )
            pessoas_instances.append(p)

        conn.close()

        # Resumo das estatísticas
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- ESTATÍSTICAS DA IMPORTAÇÃO ---'))
        self.stdout.write(f'  Total de registros processados: {stats["total"]}')
        self.stdout.write(f'    - Fornecedores (Tipo 2)     : {stats["fornecedores"]}')
        self.stdout.write(f'    - Funcionários (Tipo 3)     : {stats["funcionarios"]}')
        self.stdout.write(f'  CNPJs válidos                 : {stats["valid_cnpj"]}')
        self.stdout.write(f'  CPFs válidos                  : {stats["valid_cpf"]}')
        self.stdout.write(f'  Documentos em branco          : {stats["doc_empty"]}')
        self.stdout.write(f'  Documentos duplicados         : {stats["doc_duplicates"]} (anotados em obs)')
        self.stdout.write(f'  Cidades associadas (100%)     : {stats["cities_matched"]} / {stats["total"]}')
        self.stdout.write(f'  Números extraídos de endereço : {stats["address_numbers_extracted"]}')
        self.stdout.write(f'  E-mails extraídos com sucesso : {stats["emails_extracted"]}')
        self.stdout.write(f'  Notas/telefones do campo email: {stats["emails_notes"]} (preservados em obs)')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n[DRY-RUN] Simulação concluída com sucesso! Nenhum dado foi inserido.'))
            return

        # Execução no PostgreSQL
        self.stdout.write('\nGravando dados no PostgreSQL...')
        with transaction.atomic():
            # Se houver reatribuição de CPF
            for orig_id, digits in reassign_doc_pks.items():
                try:
                    orig_obj = Pessoas.objects.get(id=orig_id)
                    orig_obj.cnpj_cpf = None
                    orig_obj.obs = ((orig_obj.obs or '') + f'\n[CPF {formatar_cpf_cnpj(digits)} desvinculado por pertencer ao proprietário Edson Heiji Kato Junior (ID 346)]').strip()
                    orig_obj.save()
                    self.stdout.write(f'CPF {digits} desvinculado do cadastro ID {orig_id} e transferido ao proprietário (ID 346).')
                except Pessoas.DoesNotExist:
                    pass

            Pessoas.objects.bulk_create(
                pessoas_instances,
                batch_size=batch_size,
                ignore_conflicts=False
            )

            # Atualizar sequência do PostgreSQL
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT setval(
                        pg_get_serial_sequence('cadastro_pessoas', 'id'),
                        COALESCE((SELECT MAX(id) FROM cadastro_pessoas), 1)
                    );
                """)

        total_final = Pessoas.objects.count()
        total_fornecedores = Pessoas.objects.filter(tipo_pessoa=1).count()
        total_funcionarios = Pessoas.objects.filter(funcionario=True).count()
        self.stdout.write(self.style.SUCCESS('\nIMPORTAÇÃO DE FORNECEDORES/FUNCIONÁRIOS CONCLUÍDA COM SUCESSO!'))
        self.stdout.write(self.style.SUCCESS(f'Total de fornecedores cadastrados: {total_fornecedores}'))
        self.stdout.write(self.style.SUCCESS(f'Total de funcionários cadastrados: {total_funcionarios}'))
        self.stdout.write(self.style.SUCCESS(f'Total geral de pessoas no banco   : {total_final}'))

