from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from cadastro.models import Pessoas
from fiscal.models import Cest, Cfop, Ncm
from .admin import ProdutosAdmin
from .models import (
    Categoria,
    LocalizacaoEstoque,
    Marca,
    NumeroSerie,
    Produto,
    Produtos,
    UnidadeMedida,
)


class UnidadeMedidaELocalizacaoTestCase(TestCase):
    """Testa carga inicial da migration de unidades e normalização de localização."""

    def test_unidades_padrao_populada_por_migration(self):
        siglas = set(UnidadeMedida.objects.values_list('sigla', flat=True))
        self.assertTrue({'UN', 'PC', 'CX', 'KIT', 'PAR', 'MT', 'KG'}.issubset(siglas))
        self.assertTrue(UnidadeMedida.objects.get(sigla='MT').permite_fracionado)
        self.assertTrue(UnidadeMedida.objects.get(sigla='KG').permite_fracionado)
        self.assertFalse(UnidadeMedida.objects.get(sigla='UN').permite_fracionado)

    def test_normalizacao_unidade_e_localizacao(self):
        unidade = UnidadeMedida.objects.create(sigla=' rl ', descricao='Rolo de Cabo')
        self.assertEqual(unidade.sigla, 'RL')
        self.assertEqual(unidade.descricao, 'ROLO DE CABO')
        self.assertEqual(str(unidade), 'RL - ROLO DE CABO')

        loc = LocalizacaoEstoque.objects.create(codigo=' pr-a1 ', setor='depósito')
        self.assertEqual(loc.codigo, 'PR-A1')
        self.assertEqual(loc.setor, 'DEPOSITO')
        self.assertEqual(str(loc), 'PR-A1 (DEPOSITO)')


class ProdutosModelTestCase(TestCase):
    """Testa regras de negócio do modelo Produtos e comportamento do Admin."""

    def setUp(self):
        self.fornecedor = Pessoas.objects.create(
            razao_nome='Distribuidora Tech Brasil',
            juridica_fisica=0,
            tipo_pessoa=1,
        )
        self.marca = Marca.objects.create(nome='Kingston')
        self.cat_pai = Categoria.objects.create(nome='Hardware')
        self.categoria = Categoria.objects.create(nome='Armazenamento', categoria_pai=self.cat_pai)
        self.unidade = UnidadeMedida.objects.get(sigla='UN')
        self.localizacao = LocalizacaoEstoque.objects.create(codigo='COR-A-P01', setor='DEPOSITO')
        self.ncm_ssd = Ncm.objects.get(codigo='84717040')
        self.cest_ssd = Cest.objects.get(codigo='2103200')
        self.cfop_venda = Cfop.objects.get(codigo='5102')

    def test_criar_produto_informatica(self):
        produto = Produtos.objects.create(
            codigo_interno='SKU-SSD-1TB',
            codigo_barras='7891234567890',
            nome='SSD NVMe 1TB Kingston NV2 M.2 2280',
            marca=self.marca,
            modelo='SNV2S/1000G',
            part_number='SNV2S/1000G',
            categoria=self.categoria,
            unidade_medida=self.unidade,
            localizacao_estoque=self.localizacao,
            condicao='NOVO',
            preco_custo=200.00,
            preco_venda=350.00,
            estoque_atual=25,
            estoque_minimo=5,
            controla_numero_serie=True,
            garantia_meses=36,
            fornecedor=self.fornecedor,
            ncm=self.ncm_ssd,
            cest=self.cest_ssd,
            cfop=self.cfop_venda,
        )
        self.assertEqual(produto.marca.nome, 'KINGSTON')
        self.assertEqual(str(produto.categoria), 'HARDWARE > ARMAZENAMENTO')
        self.assertEqual(produto.unidade_medida.sigla, 'UN')
        self.assertEqual(produto.localizacao_estoque.codigo, 'COR-A-P01')
        self.assertEqual(produto.ncm.codigo, '84717040')
        self.assertEqual(produto.cest.codigo, '2103200')
        self.assertEqual(produto.cfop.codigo, '5102')
        self.assertEqual(produto.nome, 'SSD NVME 1TB KINGSTON NV2 M.2 2280')
        # Margem de lucro calculada automaticamente: (350 - 200) / 200 * 100 = 75.0%
        self.assertEqual(float(produto.margem_lucro), 75.0)
        self.assertTrue(produto.controla_numero_serie)
        # Com controla_numero_serie=True sem seriais cadastrados, estoque inicia zerado
        self.assertEqual(produto.estoque_atual, 0)
        self.assertEqual(produto.garantia_meses, 36)
        self.assertEqual(produto.fornecedor.razao_nome, 'DISTRIBUIDORA TECH BRASIL')
        self.assertEqual(str(produto), 'SKU-SSD-1TB - SSD NVME 1TB KINGSTON NV2 M.2 2280')

    def test_unidade_medida_padrao_un_quando_omitida(self):
        produto = Produtos.objects.create(nome='Cabo Forca ATX')
        self.assertIsNotNone(produto.unidade_medida)
        self.assertEqual(produto.unidade_medida.sigla, 'UN')

    def test_admin_estoque_atual_sempre_readonly(self):
        produto_com_serial = Produtos.objects.create(nome='GPU RTX', controla_numero_serie=True)
        produto_sem_serial = Produtos.objects.create(nome='Pasta Termica', controla_numero_serie=False)
        admin_inst = ProdutosAdmin(Produtos, AdminSite())
        request = RequestFactory().get('/')

        self.assertIn('estoque_atual', admin_inst.get_readonly_fields(request, produto_com_serial))
        self.assertIn('estoque_atual', admin_inst.get_readonly_fields(request, produto_sem_serial))

    def test_alias_produto(self):
        self.assertIs(Produto, Produtos)


class ProdutosAPITestCase(APITestCase):
    """Testa endpoints REST de produtos, categorias, marcas, unidades e localizações."""

    def setUp(self):
        self.user = User.objects.create_user(username='adminuser', password='password123')
        self.client.force_authenticate(user=self.user)
        self.marca_logitech = Marca.objects.create(nome='Logitech')
        self.cat_perifericos = Categoria.objects.create(nome='Perifericos')
        self.unidade_un = UnidadeMedida.objects.get(sigla='UN')
        self.loc_vitrine = LocalizacaoEstoque.objects.create(codigo='VIT-01', setor='VITRINE')

    def test_list_and_create_produto_api(self):
        url = reverse('produtos')
        data = {
            'codigo_interno': 'SKU-MOUSE-G203',
            'nome': 'Mouse Gamer Logitech G203 Lightsync RGB',
            'marca': self.marca_logitech.id,
            'categoria': self.cat_perifericos.id,
            'unidade_medida': self.unidade_un.id,
            'localizacao_estoque': self.loc_vitrine.id,
            'preco_custo': 80.00,
            'preco_venda': 149.90,
            'estoque_atual': 15,
            'controla_numero_serie': True,
            'garantia_meses': 24,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['codigo_interno'], 'SKU-MOUSE-G203')
        self.assertEqual(response.data['marca_nome'], 'LOGITECH')
        self.assertEqual(response.data['categoria_nome'], 'PERIFERICOS')
        self.assertEqual(response.data['unidade_medida_sigla'], 'UN')
        self.assertEqual(response.data['localizacao_estoque_codigo'], 'VIT-01')

        # Código interno vazio ("") vira None e unidade_medida omitida recebe 'UN' automaticamente
        res_blank_1 = self.client.post(url, {'nome': 'Cabo HDMI 2m', 'codigo_interno': ''}, format='json')
        res_blank_2 = self.client.post(url, {'nome': 'Cabo DisplayPort 2m', 'codigo_interno': ''}, format='json')
        self.assertEqual(res_blank_1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_blank_2.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res_blank_1.data['codigo_interno'])
        self.assertEqual(res_blank_1.data['unidade_medida_sigla'], 'UN')

        response_list = self.client.get(url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list.data), 3)

    def test_filter_produto_by_marca_unidade_e_localizacao(self):
        marca_redragon = Marca.objects.create(nome='Redragon')
        marca_razer = Marca.objects.create(nome='Razer')
        unidade_kit = UnidadeMedida.objects.get(sigla='KIT')
        loc_dep = LocalizacaoEstoque.objects.create(codigo='DEP-B2', setor='DEPOSITO')

        Produtos.objects.create(
            nome='Kit Teclado e Mouse Redragon',
            marca=marca_redragon,
            unidade_medida=unidade_kit,
            localizacao_estoque=loc_dep,
            preco_venda=200,
        )
        Produtos.objects.create(
            nome='Mouse Razer Deathadder',
            marca=marca_razer,
            unidade_medida=self.unidade_un,
            localizacao_estoque=self.loc_vitrine,
            preco_venda=250,
        )

        url = reverse('produtos')
        res_marca = self.client.get(f'{url}?marca={marca_redragon.id}')
        self.assertEqual(res_marca.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_marca.data), 1)
        self.assertEqual(res_marca.data[0]['marca_nome'], 'REDRAGON')

        res_un = self.client.get(f'{url}?unidade_medida={unidade_kit.id}')
        self.assertEqual(len(res_un.data), 1)
        self.assertEqual(res_un.data[0]['unidade_medida_sigla'], 'KIT')

        res_loc = self.client.get(f'{url}?localizacao_estoque={loc_dep.id}')
        self.assertEqual(len(res_loc.data), 1)
        self.assertEqual(res_loc.data[0]['localizacao_estoque_codigo'], 'DEP-B2')

    def test_categoria_marca_unidade_e_localizacao_endpoints(self):
        res_marca = self.client.post(reverse('marcas'), {'nome': 'Corsair'}, format='json')
        self.assertEqual(res_marca.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_marca.data['nome'], 'CORSAIR')

        res_cat = self.client.post(
            reverse('categorias'),
            {'nome': 'Mouses', 'categoria_pai': self.cat_perifericos.id},
            format='json',
        )
        self.assertEqual(res_cat.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_cat.data['categoria_pai_nome'], 'PERIFERICOS')

        res_un_list = self.client.get(reverse('unidades_medida'))
        self.assertEqual(res_un_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_un_list.data), 7)

        res_un_create = self.client.post(
            reverse('unidades_medida'),
            {'sigla': 'lt', 'descricao': 'Litro', 'permite_fracionado': True},
            format='json',
        )
        self.assertEqual(res_un_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_un_create.data['sigla'], 'LT')

        res_loc_create = self.client.post(
            reverse('localizacoes_estoque'),
            {'codigo': 'rma-01', 'setor': 'assistencia', 'descricao': 'Bancada RMA'},
            format='json',
        )
        self.assertEqual(res_loc_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_loc_create.data['codigo'], 'RMA-01')
        self.assertEqual(res_loc_create.data['setor'], 'ASSISTENCIA')


class NumeroSerieTestCase(TestCase):
    """Testa sincronização de estoque e garantia em números de série."""

    def setUp(self):
        self.fornecedor = Pessoas.objects.create(
            razao_nome='Fornecedor Hardware Ltda',
            tipo_pessoa=1,
            juridica_fisica=0,
        )
        self.cliente = Pessoas.objects.create(
            razao_nome='Joao da Silva',
            tipo_pessoa=0,
            juridica_fisica=1,
        )
        self.produto = Produtos.objects.create(
            nome='Placa de Video RTX 4060',
            preco_custo=1800,
            preco_venda=2500,
            controla_numero_serie=True,
            garantia_meses=24,
        )

    def test_sincronizacao_estoque_com_seriais(self):
        serial1 = NumeroSerie.objects.create(
            produto=self.produto,
            numero_serie='SN-RTX4060-001',
            status='DISPONIVEL',
            fornecedor=self.fornecedor,
        )
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.estoque_atual, 1)

        serial2 = NumeroSerie.objects.create(
            produto=self.produto,
            numero_serie='SN-RTX4060-002',
            status='DISPONIVEL',
            fornecedor=self.fornecedor,
        )
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.estoque_atual, 2)

        agora = timezone.now()
        serial1.status = 'VENDIDO'
        serial1.cliente = self.cliente
        serial1.data_venda = agora
        serial1.save()

        self.produto.refresh_from_db()
        self.assertEqual(self.produto.estoque_atual, 1)

        serial1.refresh_from_db()
        self.assertIsNotNone(serial1.data_fim_garantia)
        self.assertTrue(serial1.esta_em_garantia)

        serial2.delete()
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.estoque_atual, 0)


class NumeroSerieAPITestCase(APITestCase):
    """Testa endpoints REST de números de série."""

    def setUp(self):
        self.user = User.objects.create_user(username='operador', password='password123')
        self.client.force_authenticate(user=self.user)
        self.produto = Produtos.objects.create(
            nome='Processador Ryzen 7 7800X3D',
            controla_numero_serie=True,
            garantia_meses=36,
        )

    def test_create_and_list_numero_serie_api(self):
        url = reverse('numeros_serie')
        data = {
            'produto': self.produto.id,
            'numero_serie': 'SN-AMD-RYZEN-999',
            'status': 'DISPONIVEL',
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['numero_serie'], 'SN-AMD-RYZEN-999')

        response_list = self.client.get(url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list.data), 1)
        self.assertEqual(response_list.data[0]['status_display'], 'Disponível em Estoque')


class ImportarProdutosFirebirdTestCase(TestCase):
    """Testa o comando de importação de produtos a partir do Firebird."""

    def test_importar_produtos_firebird_arquivo_inexistente(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError

        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('importar_produtos_firebird', arquivo='arquivo_fantasma.fdb', stdout=out)
        self.assertIn('Arquivo Firebird não encontrado', str(ctx.exception))

    def test_importar_produtos_firebird_dry_run_execucao(self):
        import os
        from io import StringIO
        from django.conf import settings
        from django.core.management import call_command

        fdb_path = os.path.join(settings.BASE_DIR, 'INFYSK-ATUAL.FDB')
        if not os.path.exists(fdb_path):
            self.skipTest('Arquivo INFYSK-ATUAL.FDB não encontrado no ambiente de teste.')

        out = StringIO()
        call_command('importar_produtos_firebird', arquivo=fdb_path, dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn('MODO DRY-RUN ATIVADO', output)
        self.assertIn('Simulação concluída com sucesso', output)
