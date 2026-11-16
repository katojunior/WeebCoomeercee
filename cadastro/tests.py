from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth.models import User
from .admin import PessoasAdmin
from .models import Estado, Cidade, Pessoas, Pessoa, Cliente


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
