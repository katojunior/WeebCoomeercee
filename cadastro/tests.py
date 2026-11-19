from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth.models import User
from .admin import PessoasAdmin, EmpresaAdmin
from .models import Estado, Cidade, Pessoas, Pessoa, Cliente, Empresa


class PessoasModelTestCase(TestCase):
    def test_criar_pessoa_cliente(self):
        pessoa = Pessoas.objects.create(
            razao_nome='Cliente Teste',
            juridica_fisica=1,
            tipo_pessoa=0
        )
        self.assertEqual(pessoa.razao_nome, 'CLIENTE TESTE')
        self.assertEqual(pessoa.tipo_pessoa, 0)
        self.assertEqual(pessoa.get_tipo_pessoa_display(), 'CLIENTE')
        self.assertEqual(pessoa.codigo_tipo, 0)
        self.assertEqual(str(pessoa), 'CLIENTE TESTE')

    def test_criar_pessoa_fornecedor(self):
        pessoa = Pessoas.objects.create(
            razao_nome='Fornecedor Teste',
            juridica_fisica=0,
            tipo_pessoa=1
        )
        self.assertEqual(pessoa.tipo_pessoa, 1)
        self.assertEqual(pessoa.get_tipo_pessoa_display(), 'FORNECEDOR')

    def test_criar_pessoa_ambos(self):
        pessoa = Pessoas.objects.create(
            razao_nome='Parceiro Ambos Teste',
            juridica_fisica=0,
            tipo_pessoa=2
        )
        self.assertEqual(pessoa.tipo_pessoa, 2)
        self.assertEqual(pessoa.get_tipo_pessoa_display(), 'AMBOS')
        self.assertFalse(pessoa.funcionario)

    def test_campo_funcionario_boolean(self):
        func = Pessoas.objects.create(
            razao_nome='Funcionario Teste',
            juridica_fisica=1,
            tipo_pessoa=0,
            funcionario=True
        )
        self.assertTrue(func.funcionario)
        self.assertEqual(func.tipo_pessoa, 0)
        self.assertEqual(func.get_tipo_pessoa_display(), 'CLIENTE')

    def test_aliases(self):
        self.assertIs(Pessoa, Pessoas)
        self.assertIs(Cliente, Pessoas)

    def test_cnpj_cpf_unico_e_nulos_permitidos(self):
        p1 = Pessoas.objects.create(razao_nome='Sem Doc 1', juridica_fisica=1, tipo_pessoa=0, cnpj_cpf='')
        p2 = Pessoas.objects.create(razao_nome='Sem Doc 2', juridica_fisica=1, tipo_pessoa=0, cnpj_cpf=None)
        self.assertIsNone(p1.cnpj_cpf)
        self.assertIsNone(p2.cnpj_cpf)

        p3 = Pessoas.objects.create(razao_nome='Com Doc', juridica_fisica=1, tipo_pessoa=0, cnpj_cpf='52998224725')
        self.assertEqual(p3.cnpj_cpf, '529.982.247-25')
        self.assertEqual(p3.cnpj_cfp, '529.982.247-25')

    def test_validacao_cpf_cnpj_cep_e_mascaras(self):
        pessoa_valida = Pessoas(
            razao_nome='Cliente Valido',
            juridica_fisica=1,
            tipo_pessoa=0,
            cnpj_cpf='52998224725',
            cep='01001000',
            celular='11999998888',
            telefone='1133334444',
        )
        pessoa_valida.full_clean()
        pessoa_valida.save()
        self.assertEqual(pessoa_valida.cnpj_cpf, '529.982.247-25')
        self.assertEqual(pessoa_valida.cep, '01001-000')
        self.assertEqual(pessoa_valida.celular, '(11) 99999-8888')
        self.assertEqual(pessoa_valida.telefone, '(11) 3333-4444')

        with self.assertRaises(ValidationError):
            Pessoas(razao_nome='CPF Invalido', juridica_fisica=1, tipo_pessoa=0, cnpj_cpf='52998224700').full_clean()

        with self.assertRaises(ValidationError):
            Pessoas(razao_nome='CNPJ em Fisica', juridica_fisica=1, tipo_pessoa=0, cnpj_cpf='12345678000195').full_clean()

        with self.assertRaises(ValidationError):
            Pessoas(razao_nome='CEP Invalido', juridica_fisica=1, tipo_pessoa=0, cep='1234').full_clean()

    def test_pessoas_admin_carrega_script_mascaras(self):
        self.assertIn('cadastro/js/masks.js', PessoasAdmin.Media.js)

    def test_pessoas_admin_inlines_e_resumo(self):
        from django.contrib import admin
        from decimal import Decimal
        from ordem_servico.models import EquipamentoCliente, OrdemServico
        from vendas.models import Venda
        from financeiro.models import TituloFinanceiro

        pessoas_admin = admin.site._registry[Pessoas]
        self.assertEqual(len(pessoas_admin.inlines), 4)

        # Verifica que todos os inlines têm collapse e extra = 0
        for inline_cls in pessoas_admin.inlines:
            inline = inline_cls(Pessoas, admin.site)
            self.assertEqual(inline.extra, 0)
            self.assertIn('collapse', inline.classes)

        # Teste do resumo comercial e financeiro
        cliente = Pessoas.objects.create(
            razao_nome='Cliente Com Resumo',
            juridica_fisica=1,
            tipo_pessoa=0
        )
        # Cria venda
        Venda.objects.create(cliente=cliente, valor_total=Decimal('350.00'), status='FINALIZADO')
        # Cria OS
        OrdemServico.objects.create(cliente=cliente, valor_total=Decimal('120.00'), status='ORCAMENTO', finalizada=False)
        # Cria Título a receber em aberto
        TituloFinanceiro.objects.create(
            tipo='RECEBER',
            pessoa=cliente,
            descricao='VND TESTE',
            data_vencimento='2026-11-20',
            valor_original=Decimal('350.00'),
            saldo_devedor=Decimal('350.00'),
            status='ABERTO'
        )

        resumo_vendas = pessoas_admin.resumo_total_vendas(cliente)
        resumo_os = pessoas_admin.resumo_total_os(cliente)
        resumo_saldo = pessoas_admin.resumo_saldo_devedor(cliente)
        resumo_os_abertas = pessoas_admin.resumo_os_em_aberto(cliente)

        self.assertIn('350,00', resumo_vendas)
        self.assertIn('120,00', resumo_os)
        self.assertIn('350,00', resumo_saldo)
        self.assertIn('EM ABERTO', resumo_saldo)
        self.assertIn('1 ordem(ns) em andamento', resumo_os_abertas)


class PessoasAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_authenticate(user=self.user)

    def test_list_and_create_pessoa_api(self):
        url = reverse('pessoas')
        data = {
            'razao_nome': 'Empresa API Teste',
            'juridica_fisica': 0,
            'tipo_pessoa': 1,
            'cnpj_cpf': '12345678000195',
            'cep': '01001000',
            'celular': '18997571080',
            'telefone': '1832221111',
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tipo_pessoa'], 1)
        self.assertEqual(response.data['cnpj_cpf'], '12.345.678/0001-95')
        self.assertEqual(response.data['cep'], '01001-000')
        self.assertEqual(response.data['celular'], '(18) 99757-1080')
        self.assertEqual(response.data['telefone'], '(18) 3222-1111')

        # Segundo registro com mesmo CNPJ (com máscara) deve falhar na validação de unicidade
        dup_response = self.client.post(url, {
            'razao_nome': 'Empresa Duplicada',
            'juridica_fisica': 0,
            'tipo_pessoa': 1,
            'cnpj_cpf': '12.345.678/0001-95'
        }, format='json')
        self.assertEqual(dup_response.status_code, status.HTTP_400_BAD_REQUEST)

        # CPF inválido ou CEP inválido ou CPF em Pessoa Jurídica devem retornar 400
        bad_cpf = self.client.post(url, {'razao_nome': 'Invalido', 'juridica_fisica': 1, 'tipo_pessoa': 0, 'cnpj_cpf': '11111111111'}, format='json')
        bad_cep = self.client.post(url, {'razao_nome': 'CEP Ruim', 'juridica_fisica': 1, 'tipo_pessoa': 0, 'cep': '999'}, format='json')
        mismatch = self.client.post(url, {'razao_nome': 'PF com CNPJ', 'juridica_fisica': 1, 'tipo_pessoa': 0, 'cnpj_cpf': '11.222.333/0001-81'}, format='json')
        self.assertEqual(bad_cpf.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad_cep.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)

        # Dois registros com cnpj_cpf vazio ("") devem ser permitidos (convertidos para None)
        r_blank1 = self.client.post(url, {'razao_nome': 'Pessoa Sem CPF 1', 'juridica_fisica': 1, 'tipo_pessoa': 0, 'cnpj_cpf': ''}, format='json')
        r_blank2 = self.client.post(url, {'razao_nome': 'Pessoa Sem CPF 2', 'juridica_fisica': 1, 'tipo_pessoa': 0, 'cnpj_cpf': ''}, format='json')
        self.assertEqual(r_blank1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r_blank2.status_code, status.HTTP_201_CREATED)

        response_list = self.client.get(url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list.data), 3)

    def test_legacy_clientes_url(self):
        url = reverse('clientes')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EstadoCidadeAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_local', password='password123')
        self.client.force_authenticate(user=self.user)
        self.sp = Estado.objects.create(codigoUf=35, uf='SP', estado='Sao Paulo', regiao='Sudeste')
        self.rj = Estado.objects.create(codigoUf=33, uf='RJ', estado='Rio de Janeiro', regiao='Sudeste')
        self.campinas = Cidade.objects.create(descricaoCidade='Campinas', uf=self.sp, capital=False)
        self.niteroi = Cidade.objects.create(descricaoCidade='Niteroi', uf=self.rj, capital=False)

    def test_cidade_detail_route(self):
        url = reverse('cidade', kwargs={'cidade_pk': self.campinas.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['descricaoCidade'], 'CAMPINAS')

    def test_estado_cidades_nested_list_and_auto_uf_create(self):
        url = reverse('estado_cidades', kwargs={'estado_pk': self.sp.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['descricaoCidade'], 'CAMPINAS')

        # POST sem informar uf no corpo preenche automaticamente pelo estado_pk
        res_create = self.client.post(url, {'descricaoCidade': 'Santos'}, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create.data['uf'], self.sp.pk)
        self.assertEqual(res_create.data['descricao_completa'], 'SANTOS / SP')

        # POST em lote sem uf no corpo
        res_batch = self.client.post(url, [
            {'descricaoCidade': 'Sorocaba'},
            {'descricaoCidade': 'Ribeirao Preto'}
        ], format='json')
        self.assertEqual(res_batch.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cidade.objects.filter(uf=self.sp).count(), 4)

        # POST com uf divergente deve falhar
        res_conflict = self.client.post(url, {'descricaoCidade': 'Petropolis', 'uf': self.rj.pk}, format='json')
        self.assertEqual(res_conflict.status_code, status.HTTP_400_BAD_REQUEST)

    def test_estado_cidade_nested_detail_route(self):
        url_ok = reverse('estado_cidade', kwargs={'estado_pk': self.sp.pk, 'cidade_pk': self.campinas.pk})
        response_ok = self.client.get(url_ok)
        self.assertEqual(response_ok.status_code, status.HTTP_200_OK)
        self.assertEqual(response_ok.data['descricaoCidade'], 'CAMPINAS')

        # Cidade de outro estado deve retornar 404 na rota aninhada
        url_wrong = reverse('estado_cidade', kwargs={'estado_pk': self.rj.pk, 'cidade_pk': self.campinas.pk})
        response_wrong = self.client.get(url_wrong)
        self.assertEqual(response_wrong.status_code, status.HTTP_404_NOT_FOUND)

    def test_batch_create_estados(self):
        url = reverse('estados')
        payload = [
            {'codigoUf': 41, 'uf': 'PR', 'estado': 'Parana', 'regiao': 'Sul'},
            {'codigoUf': 42, 'uf': 'SC', 'estado': 'Santa Catarina', 'regiao': 'SUL'},
        ]
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Estado.objects.count(), 4)
        self.assertEqual(Estado.objects.get(uf='PR').regiao, 'SUL')

    def test_regiao_invalida_e_codigo_ibge_unico(self):
        res_bad = self.client.post(
            reverse('estados'),
            {'codigoUf': 43, 'uf': 'RS', 'estado': 'Rio Grande do Sul', 'regiao': 'INVALIDA'},
            format='json'
        )
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)

        # Cidades com codigoIbge vazio ("") são permitidas em duplicidade (convertido para None)
        url_cidades = reverse('cidades')
        r1 = self.client.post(url_cidades, {'descricaoCidade': 'Cidade A', 'uf': self.sp.pk, 'codigoIbge': ''}, format='json')
        r2 = self.client.post(url_cidades, {'descricaoCidade': 'Cidade B', 'uf': self.sp.pk, 'codigoIbge': ''}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

        # Cidades com mesmo codigoIbge preenchido devem falhar
        r3 = self.client.post(url_cidades, {'descricaoCidade': 'Cidade C', 'uf': self.sp.pk, 'codigoIbge': '3550308'}, format='json')
        r4 = self.client.post(url_cidades, {'descricaoCidade': 'Cidade D', 'uf': self.sp.pk, 'codigoIbge': '3550308'}, format='json')
        self.assertEqual(r3.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r4.status_code, status.HTTP_400_BAD_REQUEST)

    def test_importar_localidades_command_idempotente(self):
        import json
        import tempfile
        from io import StringIO
        from django.core.management import call_command

        dados = [
            {'descricaoCidade': 'São Paulo', 'uf': 35, 'codigoIbge': '3550308', 'capital': False},
            {'descricaoCidade': 'Campinas', 'uf': 35, 'codigoIbge': '3509502', 'capital': False},
        ]
        with tempfile.NamedTemporaryFile('w', suffix='.json', encoding='utf-8', delete=False) as tmp:
            json.dump(dados, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        try:
            out1 = StringIO()
            call_command('importar_localidades', arquivo=tmp_path, stdout=out1)
            self.assertEqual(Estado.objects.count(), 27)
            self.assertTrue(Cidade.objects.get(codigoIbge='3550308').capital)
            self.assertFalse(Cidade.objects.get(codigoIbge='3509502').capital)

            # Re-execução não deve duplicar
            out2 = StringIO()
            call_command('importar_localidades', arquivo=tmp_path, stdout=out2)
            self.assertEqual(Estado.objects.count(), 27)
            self.assertEqual(Cidade.objects.filter(codigoIbge__in=['3550308', '3509502']).count(), 2)
        finally:
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_importar_clientes_firebird_arquivo_inexistente(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError

        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('importar_clientes_firebird', arquivo='arquivo_fantasma.fdb', stdout=out)
        self.assertIn('Arquivo Firebird não encontrado', str(ctx.exception))

    def test_importar_clientes_firebird_dry_run_execucao(self):
        import os
        from io import StringIO
        from django.conf import settings
        from django.core.management import call_command

        fdb_path = os.path.join(settings.BASE_DIR, 'INFYSK-ATUAL.FDB')
        if not os.path.exists(fdb_path):
            self.skipTest('Arquivo INFYSK-ATUAL.FDB não encontrado no ambiente de teste.')

        out = StringIO()
        call_command('importar_clientes_firebird', arquivo=fdb_path, dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn('MODO DRY-RUN ATIVADO', output)
        self.assertIn('Simulação concluída com sucesso', output)

    def test_importar_fornecedores_firebird_arquivo_inexistente(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError

        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('importar_fornecedores_firebird', arquivo='arquivo_fantasma.fdb', stdout=out)
        self.assertIn('Arquivo Firebird não encontrado', str(ctx.exception))

    def test_importar_fornecedores_firebird_dry_run_execucao(self):
        import os
        from io import StringIO
        from django.conf import settings
        from django.core.management import call_command

        fdb_path = os.path.join(settings.BASE_DIR, 'INFYSK-ATUAL.FDB')
        if not os.path.exists(fdb_path):
            self.skipTest('Arquivo INFYSK-ATUAL.FDB não encontrado no ambiente de teste.')

        out = StringIO()
        call_command('importar_fornecedores_firebird', arquivo=fdb_path, dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn('MODO DRY-RUN ATIVADO', output)
        self.assertIn('Simulação concluída com sucesso', output)


class EmpresaModelAndAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_emp', password='password123')
        self.client.force_authenticate(user=self.user)
        self.sp = Estado.objects.create(codigoUf=35, uf='SP', estado='Sao Paulo', regiao='Sudeste')
        self.birigui = Cidade.objects.create(
            descricaoCidade='Birigui',
            uf=self.sp,
            codigoIbge='3506508',
            ddd='18',
        )

    def test_criar_empresa_cabecalho_impressao_e_aliases(self):
        emp = Empresa.objects.create(
            razao_social='Edson Heiji Kato Birigui - ME',
            nome_fantasia='Kato e Cia Informática',
            cnpj='04831858000159',
            inscricao_estadual='214.138.526-118',
            endereco='Rua Gonçalo Ibanhes',
            numero='484A',
            bairro='Centro',
            cep='16200192',
            cidade=self.birigui,
            telefone='1836421088',
            telefone2='1836429424',
            email='Contato@KatoInformatica.com.br',
            slogan='Soluções em Informática e Assistência Técnica',
            matriz=True,
        )
        self.assertEqual(emp.razao_social, 'EDSON HEIJI KATO BIRIGUI - ME')
        self.assertEqual(emp.nome_fantasia, 'KATO E CIA INFORMATICA')
        self.assertEqual(emp.cnpj, '04.831.858/0001-59')
        self.assertEqual(emp.cep, '16200-192')
        self.assertEqual(emp.telefone, '(18) 3642-1088')
        self.assertEqual(emp.telefone2, '(18) 3642-9424')
        self.assertEqual(emp.email, 'contato@katoinformatica.com.br')
        self.assertEqual(emp.codigo_ibge_cidade, '3506508')
        self.assertEqual(emp.codigo_ibge_estado, '35')
        self.assertEqual(emp.razao_empresa, 'EDSON HEIJI KATO BIRIGUI - ME')
        self.assertEqual(emp.fantasia_empresa, 'KATO E CIA INFORMATICA')
        self.assertEqual(emp.cnpj_empresa, '04.831.858/0001-59')
        self.assertEqual(emp.inscricao_empresa, '214.138.526-118')
        self.assertEqual(emp.numero_emp, '484A')

        cab = emp.dados_cabecalho_impressao
        self.assertEqual(cab['titulo'], 'KATO E CIA INFORMATICA')
        self.assertIn('CNPJ: 04.831.858/0001-59', cab['documento_formatado'])
        self.assertIn('I.E.: 214.138.526-118', cab['documento_formatado'])
        self.assertIn('RUA GONCALO IBANHES, Nº 484A', cab['endereco_completo'])
        self.assertIn('BIRIGUI/SP', cab['endereco_completo'])
        self.assertIn('(18) 3642-1088', cab['contatos_formatados'])
        self.assertEqual(Empresa.get_principal(), emp)

    def test_unicidade_matriz_e_api_principal(self):
        e1 = Empresa.objects.create(razao_social='Matriz Original', cnpj='04.831.858/0001-59', matriz=True)
        e2 = Empresa.objects.create(razao_social='Nova Matriz', cnpj='12.345.678/0001-95', matriz=True)
        e1.refresh_from_db()
        self.assertFalse(e1.matriz)
        self.assertTrue(e2.matriz)

        url = reverse('empresa_principal')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['id'], e2.id)
        self.assertIn('dados_cabecalho_impressao', res.data)

    def test_importar_empresa_firebird(self):
        import os
        from io import StringIO
        from django.conf import settings
        from django.core.management import call_command

        fdb_path = os.path.join(settings.BASE_DIR, 'INFYSK-ATUAL.FDB')
        if not os.path.exists(fdb_path):
            self.skipTest('Arquivo INFYSK-ATUAL.FDB não encontrado.')

        out = StringIO()
        call_command('importar_empresa_firebird', arquivo=fdb_path, limpar=True, stdout=out)
        emp = Empresa.get_principal()
        self.assertIsNotNone(emp)
        self.assertEqual(emp.id, 1)
        self.assertEqual(emp.razao_social, 'EDSON HEIJI KATO BIRIGUI - ME')
        self.assertEqual(emp.nome_fantasia, 'KATO E CIA INFORMATICA')
        self.assertEqual(emp.cnpj, '04.831.858/0001-59')
        self.assertEqual(emp.inscricao_estadual, '214.138.526-118')
        self.assertEqual(emp.endereco, 'RUA GONCALO IBANHES')
        self.assertEqual(emp.numero, '484A')
        self.assertEqual(emp.bairro, 'CENTRO')
        self.assertEqual(emp.cep, '16200-192')
        self.assertEqual(emp.cidade, self.birigui)
        self.assertEqual(emp.telefone, '(18) 3642-1088')
        self.assertEqual(emp.telefone2, '(18) 3642-9424')


class ExtratoClienteAdminTestCase(TestCase):
    def setUp(self):
        from datetime import datetime
        from decimal import Decimal
        from django.utils import timezone
        from cadastro_produto.models import Produtos
        from ordem_servico.models import EquipamentoCliente, OrdemServico, ItemOrdemServico
        from vendas.models import Venda, ItemVenda

        self.admin_user = User.objects.create_superuser(username='super_ext', password='123', email='ext@e.com')
        self.client.force_login(self.admin_user)

        self.empresa = Empresa.objects.create(
            razao_social='Edson Heiji Kato Birigui - ME',
            nome_fantasia='Kato e Cia Informática',
            cnpj='04.831.858/0001-59',
            chave_pix='04.831.858/0001-59',
            matriz=True,
        )
        self.cliente1 = Pessoas.objects.create(razao_nome='Cliente Extrato Alfa', juridica_fisica=1, tipo_pessoa=0)
        self.cliente2 = Pessoas.objects.create(razao_nome='Cliente Outro Beta', juridica_fisica=1, tipo_pessoa=0)
        self.produto = Produtos.objects.create(
            nome='Fonte ATX 500W',
            preco_custo=Decimal('100.00'),
            preco_venda=Decimal('180.00'),
        )
        self.eq = EquipamentoCliente.objects.create(cliente=self.cliente1, descricao='PC Desktop Gamer')

        tz = timezone.get_current_timezone()

        # Venda em aberto (finalizada=False) - R$ 180.00
        self.venda_aberta = Venda.objects.create(
            cliente=self.cliente1,
            status='ABERTO',
            finalizada=False,
            data_venda=timezone.make_aware(datetime(2026, 11, 5, 10, 0), tz),
        )
        ItemVenda.objects.create(venda=self.venda_aberta, produto=self.produto, quantidade=Decimal('1.000'))

        # Venda cancelada com finalizada=False (deve ser ocultada por padrão)
        self.venda_cancelada = Venda.objects.create(
            cliente=self.cliente1,
            status='CANCELADO',
            finalizada=False,
            data_venda=timezone.make_aware(datetime(2026, 11, 6, 10, 0), tz),
            valor_total=Decimal('999.00'),
        )

        # Venda finalizada a prazo com saldo em aberto no financeiro (R$ 360.00)
        self.venda_aprazo = Venda.objects.create(
            cliente=self.cliente1,
            status='ABERTO',
            data_venda=timezone.make_aware(datetime(2026, 11, 7, 14, 0), tz),
        )
        ItemVenda.objects.create(venda=self.venda_aprazo, produto=self.produto, quantidade=Decimal('2.000'))
        self.venda_aprazo.finalizar_venda(condicao_pagamento='CREDIARIO', numero_parcelas=2, quitada=False)

        # OS em aberto (finalizada=False) - R$ 120.00
        self.os_aberta = OrdemServico.objects.create(
            cliente=self.cliente1,
            equipamento=self.eq,
            status='EM_ANDAMENTO',
            finalizada=False,
            defeito_reclamado='Não liga',
            laudo_tecnico='Troca de fonte em análise',
            data_abertura=timezone.make_aware(datetime(2026, 11, 8, 9, 0), tz),
        )
        ItemOrdemServico.objects.create(
            ordem=self.os_aberta,
            tipo_item='SERVICO',
            descricao_personalizada='Mão de obra diagnóstico',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('120.00'),
        )

        # OS de outro cliente
        self.os_outro = OrdemServico.objects.create(
            cliente=self.cliente2,
            status='ORCAMENTO',
            finalizada=False,
            data_abertura=timezone.make_aware(datetime(2026, 11, 8, 9, 0), tz),
        )

    def test_resumo_cliente_em_aberto_e_somatoria(self):
        from decimal import Decimal

        url = reverse('admin:cadastro_extratocliente_changelist')
        res = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ocultar_cancelados': '1',
        })
        self.assertEqual(res.status_code, 200)
        dados = res.context['dados']
        self.assertEqual(dados['qtd_vendas'], 1)
        self.assertEqual(dados['qtd_os'], 1)
        self.assertEqual(dados['total_vendas'], Decimal('180.00'))
        self.assertEqual(dados['total_os'], Decimal('120.00'))
        self.assertEqual(dados['total_geral'], Decimal('300.00'))
        self.assertEqual(dados['em_aberto_geral'], Decimal('300.00'))
        self.assertContains(res, f'VND #{self.venda_aberta.id:06d}')
        self.assertContains(res, f'OS #{self.os_aberta.id:06d}')
        self.assertNotContains(res, f'VND #{self.venda_cancelada.id:06d}')

    def test_resumo_inclui_pendencia_financeira_e_filtro_data(self):
        from decimal import Decimal

        url = reverse('admin:cadastro_extratocliente_changelist')
        res = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos_ou_financeiro',
            'data_inicio': '2026-11-07',
            'data_fim': '2026-11-08',
            'ocultar_cancelados': '1',
        })
        self.assertEqual(res.status_code, 200)
        dados = res.context['dados']
        # Inclui venda_aprazo (360) + os_aberta (120) = 480 em aberto
        self.assertEqual(dados['qtd_total'], 2)
        self.assertEqual(dados['em_aberto_geral'], Decimal('480.00'))

    def test_imprimir_todos_detalhados_com_capa_e_selecao_parcial(self):
        url = reverse('admin:cadastro_extratocliente_changelist')
        res = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ocultar_cancelados': '1',
            'imprimir_todos': '1',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Extrato Consolidado')
        self.assertContains(res, 'KATO E CIA INFORMATICA')
        self.assertContains(res, 'FONTE ATX 500W')
        self.assertContains(res, 'Mão de obra diagnóstico')
        self.assertContains(res, 'batch-page')

        # Seleção parcial por checkbox: apenas a OS
        res_sel = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'imprimir_todos': '1',
            'sel': f'OS-{self.os_aberta.id}',
        })
        self.assertEqual(res_sel.status_code, 200)
        self.assertContains(res_sel, 'Mão de obra diagnóstico')
        self.assertNotContains(res_sel, 'FONTE ATX 500W')

        # Impressão somente do resumo
        res_resumo = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'acao': 'imprimir_resumo',
        })
        self.assertEqual(res_resumo.status_code, 200)
        self.assertContains(res_resumo, 'Relação Resumida dos Documentos')
        self.assertNotContains(res_resumo, 'Mão de obra diagnóstico')

    def test_exportar_csv_e_busca_clientes_e_atalhos(self):
        url = reverse('admin:cadastro_extratocliente_changelist')
        res_csv = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'exportar': 'csv',
        })
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('text/csv', res_csv['Content-Type'])
        body = res_csv.content.decode('utf-8-sig')
        self.assertIn('TOTAL GERAL', body)
        self.assertIn('300,00', body)

        url_busca = reverse('admin:cadastro_extratocliente_buscar_clientes')
        res_busca = self.client.get(url_busca, {'q': 'Alfa'})
        self.assertEqual(res_busca.status_code, 200)
        results = res_busca.json()['results']
        self.assertTrue(any(r['id'] == self.cliente1.pk for r in results))

        # Verifica atalhos em Pessoas, Venda e OrdemServico
        res_pessoa = self.client.get(reverse('admin:cadastro_pessoas_change', args=[self.cliente1.pk]))
        self.assertContains(res_pessoa, 'Resumo / Extrato de Vendas e OS')

        res_vendas = self.client.get(reverse('admin:vendas_venda_changelist'))
        self.assertContains(res_vendas, 'Resumo / Extrato por Cliente')

        res_os = self.client.get(reverse('admin:ordem_servico_ordemservico_changelist'))
        self.assertContains(res_os, 'Resumo / Extrato por Cliente')

    def test_ordenacao_crescente_decrescente_tela_impressao_csv(self):
        url = reverse('admin:cadastro_extratocliente_changelist')

        # Padrão (data desc): OS (dia 08, R$ 120) antes da Venda (dia 05, R$ 180)
        res_desc = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ordenar_por': 'data',
            'direcao': 'desc',
        })
        self.assertEqual(res_desc.status_code, 200)
        chaves_desc = [r['chave'] for r in res_desc.context['dados']['registros']]
        self.assertEqual(chaves_desc, [f'OS-{self.os_aberta.id}', f'V-{self.venda_aberta.id}'])

        # Data crescente (asc): Venda (dia 05) antes da OS (dia 08)
        res_asc = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ordenar_por': 'data',
            'direcao': 'asc',
        })
        self.assertEqual(res_asc.status_code, 200)
        chaves_asc = [r['chave'] for r in res_asc.context['dados']['registros']]
        self.assertEqual(chaves_asc, [f'V-{self.venda_aberta.id}', f'OS-{self.os_aberta.id}'])

        # Ordenar por valor_total decrescente: Venda (180) antes da OS (120)
        res_val_desc = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ordenar_por': 'valor_total',
            'direcao': 'desc',
        })
        chaves_val = [r['chave'] for r in res_val_desc.context['dados']['registros']]
        self.assertEqual(chaves_val, [f'V-{self.venda_aberta.id}', f'OS-{self.os_aberta.id}'])

        # Ordenar por valor_total crescente na impressão em lote
        res_print_asc = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ordenar_por': 'valor_total',
            'direcao': 'asc',
            'imprimir_todos': '1',
        })
        self.assertEqual(res_print_asc.status_code, 200)
        self.assertContains(res_print_asc, 'Valor Total (Crescente)')
        body_print = res_print_asc.content.decode('utf-8')
        # Na capa (tabela resumo), a OS (120) aparece antes da Venda (180)
        self.assertLess(
            body_print.find(f'OS #{self.os_aberta.id:06d}'),
            body_print.find(f'VND #{self.venda_aberta.id:06d}'),
        )
        # Nas páginas detalhadas seguintes, a OS detalhada também aparece antes da Venda detalhada
        self.assertLess(body_print.find('Mão de obra diagnóstico'), body_print.rfind('FONTE ATX 500W'))

        # Ordenação aplicada no CSV
        res_csv_asc = self.client.get(url, {
            'cliente': self.cliente1.pk,
            'situacao': 'abertos',
            'ordenar_por': 'data',
            'direcao': 'asc',
            'exportar': 'csv',
        })
        csv_text = res_csv_asc.content.decode('utf-8-sig')
        self.assertLess(csv_text.find(f'VND #{self.venda_aberta.id:06d}'), csv_text.find(f'OS #{self.os_aberta.id:06d}'))

