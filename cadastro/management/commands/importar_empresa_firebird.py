import datetime
import re
import struct
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

from cadastro.models import Cidade, Empresa
from cadastro.validators import (
    apenas_digitos,
    formatar_cep,
    formatar_cpf_cnpj,
    formatar_telefone,
)

ADDRESS_SPLIT_REGEX = re.compile(
    r'^(.*?)[,\s]+(?:N[º°.]?\s*)?(\d+[A-Za-z]?|S/?N)(?:[,\s;\-]+(.*))?$',
    re.IGNORECASE,
)


def _rle_decompress(buf):
    out = bytearray()
    i = 0
    n = len(buf)
    while i < n:
        ctrl = struct.unpack_from('b', buf, i)[0]
        i += 1
        if ctrl > 0:
            out.extend(buf[i : i + ctrl])
            i += ctrl
        elif ctrl < 0:
            count = -ctrl
            if i < n:
                out.extend(bytes([buf[i]]) * count)
                i += 1
        else:
            break
    return bytes(out)


def _ler_empresa_direto_fdb(caminho_arquivo: Path):
    """
    Lê os registros da tabela EMPRESA diretamente das páginas de dados (ODS 11)
    do arquivo .FDB caso o serviço Firebird (porta 3050) não esteja em execução.
    """
    data = caminho_arquivo.read_bytes()
    if len(data) < 4096:
        raise CommandError('Arquivo .FDB inválido ou corrompido.')

    page_size = struct.unpack_from('<H', data, 16)[0] or 4096
    num_pages = len(data) // page_size
    base_date = datetime.date(1858, 11, 17)

    def decode_fb_ts(b):
        days, t = struct.unpack('<ii', b)
        if days == 0 and t == 0:
            return None
        d = base_date + datetime.timedelta(days=days)
        secs = t // 10000
        return datetime.datetime.combine(
            d,
            datetime.time(secs // 3600, (secs % 3600) // 60, secs % 60),
        )

    def decode_fb_date(b):
        (days,) = struct.unpack('<i', b)
        if days == 0:
            return None
        return base_date + datetime.timedelta(days=days)

    def decode_varchar(b):
        ln = struct.unpack_from('<H', b, 0)[0]
        ln = min(ln, max(0, len(b) - 2))
        return b[2 : 2 + ln].decode('cp1252', errors='replace')

    # Localiza o relation_id da tabela EMPRESA em RDB$RELATIONS (rel_id = 6)
    empresa_rel_id = 135
    for p in range(num_pages):
        off = p * page_size
        if data[off] == 5:
            _, rel_id, count = struct.unpack_from('<iHH', data, off + 16)
            if rel_id == 6:
                for idx in range(count):
                    ro, rl = struct.unpack_from('<HH', data, off + 24 + idx * 4)
                    if rl == 0:
                        continue
                    rraw = data[off + ro : off + ro + rl]
                    _, _, _, rflags, _ = struct.unpack_from('<IIHHB', rraw, 0)
                    if rflags & 1:
                        continue
                    dec = _rle_decompress(rraw[13:])
                    if len(dec) >= 71 and dec[40:71].decode('latin1', errors='replace').strip() == 'EMPRESA':
                        empresa_rel_id = struct.unpack_from('<H', dec, 32)[0]
                        break

    registros = []
    for p in range(num_pages):
        off = p * page_size
        if data[off] == 5:
            _, rel_id, count = struct.unpack_from('<iHH', data, off + 16)
            if rel_id == empresa_rel_id:
                for idx in range(count):
                    ro, rl = struct.unpack_from('<HH', data, off + 24 + idx * 4)
                    if rl == 0:
                        continue
                    rraw = data[off + ro : off + ro + rl]
                    _, _, _, rflags, _ = struct.unpack_from('<IIHHB', rraw, 0)
                    if rflags & 1:
                        continue
                    decomp = _rle_decompress(rraw[13:])
                    if len(decomp) < 570:
                        continue
                    null_bits = struct.unpack_from('<I', decomp, 0)[0]

                    def is_null(fid):
                        return bool(null_bits & (1 << fid))

                    registros.append({
                        'DATA_HORA_ATUALIZADA': None if is_null(0) else decode_fb_ts(decomp[8:16]),
                        'DATA_HORA': None if is_null(1) else decode_fb_ts(decomp[16:24]),
                        'BAIRRO_EMPRESA': None if is_null(2) else decode_varchar(decomp[24:56]),
                        'DATA_CADASTRO_EMPRESA': None if is_null(3) else decode_fb_date(decomp[56:60]),
                        'DT_FUND_EMPRESA': None if is_null(4) else decode_fb_date(decomp[60:64]),
                        'CNPJ_EMPRESA': None if is_null(5) else decode_varchar(decomp[64:84]),
                        'CAIXA_POSTAL_EMPRESA': None if is_null(6) else struct.unpack('<i', decomp[84:88])[0],
                        'CODIGO_EMPRESA': None if is_null(7) else struct.unpack('<i', decomp[88:92])[0],
                        'NUMERO_EMP': None if is_null(8) else decode_varchar(decomp[92:104]),
                        'CODIGO_IBGE_CIDADE': None if is_null(9) else decode_varchar(decomp[104:116]),
                        'CODIGO_IBGE_ESTADO': None if is_null(10) else decode_varchar(decomp[116:120]),
                        'USUARIO_ATUALIZOU': None if is_null(11) else decode_varchar(decomp[120:222]),
                        'USUARIO': None if is_null(12) else decode_varchar(decomp[222:324]),
                        'ENDERECO_EMPRESA': None if is_null(13) else decode_varchar(decomp[324:366]),
                        'FANTASIA_EMPRESA': None if is_null(14) else decode_varchar(decomp[366:408]),
                        'RAZAO_EMPRESA': None if is_null(15) else decode_varchar(decomp[408:450]),
                        'CIDADE': None if is_null(16) else decode_varchar(decomp[450:508]),
                        'TELEFONE': None if is_null(18) else decode_varchar(decomp[508:524]),
                        'INSCRICAO_EMPRESA': None if is_null(19) else decode_varchar(decomp[524:542]),
                        'CEP_EMPRESA': None if is_null(20) else decode_varchar(decomp[542:554]),
                        'TELEFONE2': None if is_null(21) else decode_varchar(decomp[554:570]),
                    })
    return registros


class Command(BaseCommand):
    help = 'Importa o cadastro da Empresa da tabela EMPRESA do banco legado Firebird (.FDB) para o Django.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--arquivo',
            type=str,
            default=str(Path(settings.BASE_DIR) / 'INFYSK-ATUAL.FDB'),
            help='Caminho completo do arquivo de banco Firebird .FDB (padrão: INFYSK-ATUAL.FDB na raiz).',
        )
        parser.add_argument(
            '--host',
            type=str,
            default='localhost',
            help='Host do servidor Firebird (padrão: localhost).',
        )
        parser.add_argument(
            '--porta',
            type=int,
            default=3050,
            help='Porta do servidor Firebird (padrão: 3050).',
        )
        parser.add_argument(
            '--usuario',
            type=str,
            default='SYSDBA',
            help='Usuário do Firebird (padrão: SYSDBA).',
        )
        parser.add_argument(
            '--senha',
            type=str,
            default='masterkey',
            help='Senha do Firebird (padrão: masterkey).',
        )
        parser.add_argument(
            '--limpar',
            action='store_true',
            help='Remove os registros existentes em cadastro_empresa antes de importar.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Executa toda a leitura, validação e mapeamento sem salvar no banco de dados.',
        )

    def _obter_registros_firebird(self, caminho_arquivo, host, porta, usuario, senha):
        if firebirdsql is not None:
            try:
                conn = firebirdsql.connect(
                    host=host,
                    port=porta,
                    database=str(caminho_arquivo.resolve()),
                    user=usuario,
                    password=senha,
                    charset='WIN1252',
                )
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        CODIGO_EMPRESA,
                        RAZAO_EMPRESA,
                        FANTASIA_EMPRESA,
                        ENDERECO_EMPRESA,
                        NUMERO_EMP,
                        BAIRRO_EMPRESA,
                        CEP_EMPRESA,
                        CAIXA_POSTAL_EMPRESA,
                        INSCRICAO_EMPRESA,
                        CNPJ_EMPRESA,
                        DT_FUND_EMPRESA,
                        DATA_CADASTRO_EMPRESA,
                        TELEFONE,
                        TELEFONE2,
                        CIDADE,
                        "CODIGO_IBGE CIDADE" AS CODIGO_IBGE_CIDADE,
                        CODIGO_IBGE_ESTADO,
                        USUARIO,
                        USUARIO_ATUALIZOU,
                        DATA_HORA,
                        DATA_HORA_ATUALIZADA
                    FROM EMPRESA
                    ORDER BY CODIGO_EMPRESA
                """)
                rows = cur.fetchall()
                cols = [d[0].strip() for d in cur.description]
                conn.close()
                return [dict(zip(cols, r)) for r in rows]
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f'Aviso: Servidor Firebird indisponível em {host}:{porta} ({exc}). '
                        f'Lendo dados diretamente do arquivo {caminho_arquivo.name}...'
                    )
                )

        return _ler_empresa_direto_fdb(caminho_arquivo)

    def _resolver_cidade(self, ibge_cidade, cidade_texto):
        if ibge_cidade:
            cid = Cidade.objects.filter(codigoIbge=ibge_cidade).first()
            if cid:
                return cid

        if cidade_texto:
            texto = unidecode(str(cidade_texto)).upper().strip()
            if '-' in texto:
                nome_cid, uf_sigla = [p.strip() for p in texto.rsplit('-', 1)]
                cid = Cidade.objects.filter(descricaoCidade__iexact=nome_cid, uf__uf__iexact=uf_sigla).first()
                if cid:
                    return cid
            cid = Cidade.objects.filter(descricaoCidade__iexact=texto).first()
            if cid:
                return cid
        return None

    def handle(self, *args, **options):
        caminho_arquivo = Path(options['arquivo'])
        if not caminho_arquivo.exists():
            raise CommandError(f'Arquivo Firebird não encontrado: {caminho_arquivo}')

        host = options['host']
        porta = options['porta']
        usuario = options['usuario']
        senha = options['senha']
        limpar = options['limpar']
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING('=== INICIANDO IMPORTAÇÃO DE EMPRESA (FIREBIRD -> DJANGO) ==='))
        self.stdout.write(f'Arquivo: {caminho_arquivo}')
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN ATIVADO: Nenhuma alteração será gravada no banco.'))

        registros = self._obter_registros_firebird(caminho_arquivo, host, porta, usuario, senha)
        self.stdout.write(f'Total de registros encontrados em EMPRESA: {len(registros)}')

        if not registros:
            self.stdout.write(self.style.WARNING('Nenhum registro encontrado na tabela EMPRESA.'))
            return

        tz = timezone.get_current_timezone()
        importados = 0

        with transaction.atomic():
            if limpar and not dry_run:
                removidos, _ = Empresa.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'Registros anteriores removidos: {removidos}'))

            for idx, row in enumerate(registros):
                codigo = int(row.get('CODIGO_EMPRESA') or (idx + 1))
                razao = unidecode(str(row.get('RAZAO_EMPRESA') or '')).upper().strip() or f'EMPRESA #{codigo}'
                fantasia_raw = str(row.get('FANTASIA_EMPRESA') or '').strip()
                fantasia = unidecode(fantasia_raw).upper().strip() if fantasia_raw else None

                cnpj_raw = str(row.get('CNPJ_EMPRESA') or '').strip()
                cnpj = formatar_cpf_cnpj(cnpj_raw) if apenas_digitos(cnpj_raw) else None

                ie_raw = str(row.get('INSCRICAO_EMPRESA') or '').strip()
                inscricao_estadual = unidecode(ie_raw).upper().strip() if ie_raw else None

                end_raw = unidecode(str(row.get('ENDERECO_EMPRESA') or '')).upper().strip()
                num_raw = unidecode(str(row.get('NUMERO_EMP') or '')).upper().strip()
                complemento = None

                if end_raw and not num_raw:
                    m = ADDRESS_SPLIT_REGEX.match(end_raw)
                    if m:
                        end_raw = m.group(1).strip(' ,;-')
                        num_raw = m.group(2).strip()
                        if m.group(3):
                            complemento = m.group(3).strip(' ,;-')

                endereco = end_raw or None
                numero = num_raw or None

                bairro_raw = str(row.get('BAIRRO_EMPRESA') or '').strip()
                bairro = unidecode(bairro_raw).upper().strip() if bairro_raw else None

                cep_raw = str(row.get('CEP_EMPRESA') or '').strip()
                cep = formatar_cep(cep_raw) if apenas_digitos(cep_raw) else None

                cx_raw = row.get('CAIXA_POSTAL_EMPRESA')
                caixa_postal = str(cx_raw).strip() if cx_raw not in (None, '', 0, '0') else None

                ibge_cidade = str(row.get('CODIGO_IBGE_CIDADE') or '').strip()
                cidade_texto = str(row.get('CIDADE') or '').strip()
                cidade_obj = self._resolver_cidade(ibge_cidade, cidade_texto)

                tel1_raw = str(row.get('TELEFONE') or '').strip()
                telefone = formatar_telefone(tel1_raw) if tel1_raw else None

                tel2_raw = str(row.get('TELEFONE2') or '').strip()
                telefone2 = formatar_telefone(tel2_raw) if tel2_raw else None

                dt_fund = row.get('DT_FUND_EMPRESA')
                dt_cad = row.get('DATA_CADASTRO_EMPRESA')
                dt_hora = row.get('DATA_HORA')
                dt_atualizada = row.get('DATA_HORA_ATUALIZADA')

                if dt_hora and timezone.is_naive(dt_hora):
                    dt_hora = timezone.make_aware(dt_hora, tz)
                elif not dt_hora and dt_cad:
                    dt_hora = timezone.make_aware(datetime.datetime.combine(dt_cad, datetime.time(0, 0)), tz)

                if dt_atualizada and timezone.is_naive(dt_atualizada):
                    dt_atualizada = timezone.make_aware(dt_atualizada, tz)

                usu = unidecode(str(row.get('USUARIO') or '')).upper().strip() or 'IMPORTACAO_FB'
                usu_atu = unidecode(str(row.get('USUARIO_ATUALIZOU') or '')).upper().strip() or None

                dados_empresa = {
                    'razao_social': razao,
                    'nome_fantasia': fantasia,
                    'cnpj': cnpj,
                    'inscricao_estadual': inscricao_estadual,
                    'regime_tributario': 1,  # Simples Nacional (ME)
                    'endereco': endereco,
                    'numero': numero,
                    'complemento': complemento,
                    'bairro': bairro,
                    'cep': cep,
                    'cidade': cidade_obj,
                    'caixa_postal': caixa_postal,
                    'telefone': telefone,
                    'telefone2': telefone2,
                    'data_fundacao': dt_fund,
                    'matriz': (idx == 0),
                    'ativa': True,
                    'usuario': usu,
                    'usuario_atualizou': usu_atu,
                }

                self.stdout.write(
                    f"  -> Empresa #{codigo}: {fantasia or razao} ({razao}) | "
                    f"CNPJ: {cnpj} | I.E.: {inscricao_estadual} | "
                    f"End: {endereco}, {numero} - {bairro} - {cidade_obj or cidade_texto} - CEP {cep} | "
                    f"Fones: {telefone} / {telefone2}"
                )

                if not dry_run:
                    emp, created = Empresa.objects.update_or_create(
                        id=codigo,
                        defaults=dados_empresa,
                    )
                    update_ts = {}
                    if dt_hora:
                        update_ts['data_hora'] = dt_hora
                    if dt_atualizada:
                        update_ts['data_hora_atualizada'] = dt_atualizada
                    if update_ts:
                        Empresa.objects.filter(pk=emp.pk).update(**update_ts)
                    importados += 1

            if not dry_run and connection.vendor == 'postgresql':
                with connection.cursor() as pg_cur:
                    pg_cur.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('cadastro_empresa', 'id'),
                            COALESCE((SELECT MAX(id) FROM cadastro_empresa), 1),
                            true
                        );
                    """)

        if dry_run:
            self.stdout.write(self.style.SUCCESS('Validação DRY-RUN concluída com sucesso!'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Importação concluída com sucesso! {importados} empresa(s) gravada(s).'))
