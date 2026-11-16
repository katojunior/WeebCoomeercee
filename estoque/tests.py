from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cadastro.models import Pessoas
from cadastro_produto.models import LocalizacaoEstoque, NumeroSerie, Produtos
from .admin import EstoqueLocalizacaoAdmin, MovimentacaoEstoqueAdmin, MovimentacaoEstoqueForm
from .models import EstoqueLocalizacao, MovimentacaoEstoque
from .services import registrar_movimentacao


class MovimentacaoEstoqueServiceTestCase(TestCase):
    """Testa movimentações sem S/N, com S/N, transferências, snapshots e imutabilidade."""

    def setUp(self):
        self.fornecedor = Pessoas.objects.create(razao_nome='Fornecedor Alpha', juridica_fisica=0, tipo_pessoa=1)
        self.cliente = Pessoas.objects.create(razao_nome='Cliente Beta', juridica_fisica=1, tipo_pessoa=0)
        self.loc_dep = LocalizacaoEstoque.objects.create(codigo='DEP-01', setor='DEPOSITO')
        self.loc_vit = LocalizacaoEstoque.objects.create(codigo='VIT-01', setor='VITRINE')
        self.loc_inativa = LocalizacaoEstoque.objects.create(codigo='OLD-01', setor='OBSOLETO', ativo=False)

        self.prod_simples = Produtos.objects.create(nome='Mouse Pad Gamer', controla_numero_serie=False)
        self.prod_serial = Produtos.objects.create(
            nome='SSD 1TB NVMe',
            controla_numero_serie=True,
            garantia_meses=36,
        )

    def test_fluxo_entrada_transferencia_ajuste_saida_sem_serial(self):
        mov_ent = registrar_movimentacao(
            produto=self.prod_simples,
            tipo='ENTRADA',
            quantidade=10,
            localizacao_destino=self.loc_dep,
            pessoa=self.fornecedor,
            documento_referencia='NF-100',
        )
        self.prod_simples.refresh_from_db()
        self.assertEqual(self.prod_simples.estoque_atual, 10)
        self.assertEqual(mov_ent.saldo_anterior_produto, 0)
        self.assertEqual(mov_ent.saldo_posterior_produto, 10)
        self.assertEqual(mov_ent.saldo_posterior_destino, 10)

        mov_transf = registrar_movimentacao(
            produto=self.prod_simples,
            tipo='TRANSFERENCIA',
            quantidade=4,
            localizacao_origem=self.loc_dep,
            localizacao_destino=self.loc_vit,
            motivo='Abastecer vitrine',
        )
        self.prod_simples.refresh_from_db()
        self.assertEqual(self.prod_simples.estoque_atual, 10)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_simples, localizacao=self.loc_dep).quantidade, 6)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_simples, localizacao=self.loc_vit).quantidade, 4)
        self.assertEqual(mov_transf.saldo_anterior_origem, 10)
        self.assertEqual(mov_transf.saldo_posterior_origem, 6)
        self.assertEqual(mov_transf.saldo_anterior_destino, 0)
        self.assertEqual(mov_transf.saldo_posterior_destino, 4)

        # Ajuste negativo sem motivo deve falhar
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_simples,
                tipo='AJUSTE_SAIDA',
                quantidade=1,
                localizacao_origem=self.loc_dep,
            )

        # Saída acima do saldo disponível na vitrine deve falhar
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_simples,
                tipo='SAIDA',
                quantidade=5,
                localizacao_origem=self.loc_vit,
            )

        # Ajuste positivo e saída válida
        registrar_movimentacao(
            produto=self.prod_simples,
            tipo='AJUSTE_ENTRADA',
            quantidade=2,
            localizacao_destino=self.loc_dep,
            motivo='Contagem de inventario',
        )
        registrar_movimentacao(
            produto=self.prod_simples,
            tipo='SAIDA',
            quantidade=3,
            localizacao_origem=self.loc_vit,
            pessoa=self.cliente,
            documento_referencia='PED-55',
        )
        self.prod_simples.refresh_from_db()
        self.assertEqual(self.prod_simples.estoque_atual, 9)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_simples, localizacao=self.loc_dep).quantidade, 8)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_simples, localizacao=self.loc_vit).quantidade, 1)

    def test_destino_inativo_e_origem_igual_destino_rejeitados(self):
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_simples,
                tipo='ENTRADA',
                quantidade=2,
                localizacao_destino=self.loc_inativa,
            )
        registrar_movimentacao(
            produto=self.prod_simples,
            tipo='ENTRADA',
            quantidade=2,
            localizacao_destino=self.loc_dep,
        )
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_simples,
                tipo='TRANSFERENCIA',
                quantidade=1,
                localizacao_origem=self.loc_dep,
                localizacao_destino=self.loc_dep,
            )

    def test_movimentacao_com_numeros_serie_e_transferencia(self):
        mov_ent = registrar_movimentacao(
            produto=self.prod_serial,
            tipo='ENTRADA',
            quantidade=2,
            localizacao_destino=self.loc_dep,
            numeros_serie_novos=['sn-ssd-01', 'sn-ssd-02'],
            pessoa=self.fornecedor,
            documento_referencia='NF-777',
        )
        sn1 = NumeroSerie.objects.get(numero_serie='SN-SSD-01')
        sn2 = NumeroSerie.objects.get(numero_serie='SN-SSD-02')
        self.prod_serial.refresh_from_db()
        self.assertEqual(self.prod_serial.estoque_atual, 2)
        self.assertEqual(sn1.localizacao_estoque, self.loc_dep)
        self.assertEqual(sn1.fornecedor, self.fornecedor)
        self.assertEqual(mov_ent.numeros_serie.count(), 2)

        # Transferência de 1 serial específico do Depósito para a Vitrine
        registrar_movimentacao(
            produto=self.prod_serial,
            tipo='TRANSFERENCIA',
            quantidade=1,
            localizacao_origem=self.loc_dep,
            localizacao_destino=self.loc_vit,
            numeros_serie=[sn1],
        )
        sn1.refresh_from_db()
        self.prod_serial.refresh_from_db()
        self.assertEqual(sn1.localizacao_estoque, self.loc_vit)
        self.assertEqual(self.prod_serial.estoque_atual, 2)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_serial, localizacao=self.loc_dep).quantidade, 1)
        self.assertEqual(EstoqueLocalizacao.objects.get(produto=self.prod_serial, localizacao=self.loc_vit).quantidade, 1)

        # Tentar dar saída de sn2 informando origem VIT-01 (onde só há sn1) deve falhar
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_serial,
                tipo='SAIDA',
                quantidade=1,
                localizacao_origem=self.loc_vit,
                numeros_serie=[sn2],
                pessoa=self.cliente,
            )

        # Saída correta de sn1 pela vitrine
        registrar_movimentacao(
            produto=self.prod_serial,
            tipo='SAIDA',
            quantidade=1,
            localizacao_origem=self.loc_vit,
            numeros_serie=[sn1],
            pessoa=self.cliente,
            documento_referencia='NF-VENDA-9',
        )
        sn1.refresh_from_db()
        self.prod_serial.refresh_from_db()
        self.assertEqual(sn1.status, 'VENDIDO')
        self.assertIsNone(sn1.localizacao_estoque)
        self.assertEqual(sn1.cliente, self.cliente)
        self.assertIsNotNone(sn1.data_fim_garantia)
        self.assertEqual(self.prod_serial.estoque_atual, 1)

    def test_movimentacao_imutavel_no_model_e_admin(self):
        mov = registrar_movimentacao(
            produto=self.prod_simples,
            tipo='ENTRADA',
            quantidade=3,
            localizacao_destino=self.loc_dep,
        )
        mov.quantidade = 99
        with self.assertRaises(ValidationError):
            mov.save()
        with self.assertRaises(ValidationError):
            mov.delete()

        request = RequestFactory().get('/')
        mov_admin = MovimentacaoEstoqueAdmin(MovimentacaoEstoque, AdminSite())
        saldo_admin = EstoqueLocalizacaoAdmin(EstoqueLocalizacao, AdminSite())
        self.assertFalse(mov_admin.has_change_permission(request, mov))
        self.assertFalse(mov_admin.has_delete_permission(request, mov))
        self.assertFalse(saldo_admin.has_add_permission(request))
        self.assertFalse(saldo_admin.has_change_permission(request))
        self.assertFalse(saldo_admin.has_delete_permission(request))

        # Fieldsets no detalhe somente leitura não incluem o campo de entrada 'numeros_serie_novos'
        self.assertNotIn('numeros_serie_novos', mov_admin.get_fieldsets(request, mov)[1][1]['fields'])
        self.assertIn('numeros_serie_novos', mov_admin.get_fieldsets(request, None)[1][1]['fields'])

        # Admin form valida lista de novos seriais para entrada e add_view executa save_model + save_related
        form = MovimentacaoEstoqueForm(data={
            'produto': self.prod_serial.pk,
            'tipo': 'ENTRADA',
            'quantidade': 2,
            'localizacao_destino': self.loc_dep.pk,
            'numeros_serie_novos': 'FORM-SN-1\nFORM-SN-2',
        })
        self.assertTrue(form.is_valid(), form.errors)

        superuser = User.objects.create_superuser(username='admin_est', password='password123', email='a@a.com')
        self.client.force_login(superuser)
        res_admin = self.client.post(
            '/admin/estoque/movimentacaoestoque/add/',
            {
                'produto': self.prod_serial.pk,
                'tipo': 'ENTRADA',
                'quantidade': 2,
                'localizacao_destino': self.loc_dep.pk,
                'numeros_serie_novos': 'ADM-SN-01\nADM-SN-02',
            },
        )
        self.assertEqual(res_admin.status_code, 302)
        self.prod_serial.refresh_from_db()
        self.assertEqual(self.prod_serial.estoque_atual, 2)
        self.assertTrue(NumeroSerie.objects.filter(numero_serie='ADM-SN-01', localizacao_estoque=self.loc_dep).exists())
        self.assertTrue(NumeroSerie.objects.filter(numero_serie='ADM-SN-02', localizacao_estoque=self.loc_dep).exists())


class EstoqueAPITestCase(APITestCase):
    """Testa endpoints auditáveis de saldos e movimentações de estoque."""

    def setUp(self):
        self.user = User.objects.create_user(username='estoquista', password='password123')
        self.client.force_authenticate(user=self.user)
        self.loc_dep = LocalizacaoEstoque.objects.create(codigo='DEP-A1', setor='DEPOSITO')
        self.loc_vit = LocalizacaoEstoque.objects.create(codigo='VIT-A1', setor='VITRINE')
        self.produto = Produtos.objects.create(nome='Fonte 650W', controla_numero_serie=True, garantia_meses=12)

    def test_movimentacao_api_entrada_transferencia_e_somente_leitura(self):
        url_movs = reverse('movimentacoes_estoque')
        res_ent = self.client.post(
            url_movs,
            {
                'produto': self.produto.id,
                'tipo': 'ENTRADA',
                'quantidade': 2,
                'localizacao_destino': self.loc_dep.id,
                'numeros_serie_novos': ['PSU-001', 'PSU-002'],
                'documento_referencia': 'NF-10',
            },
            format='json',
        )
        self.assertEqual(res_ent.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ent.data['usuario'], 'estoquista')
        self.assertEqual(res_ent.data['saldo_anterior_produto'], 0)
        self.assertEqual(res_ent.data['saldo_posterior_produto'], 2)
        self.assertEqual(sorted(res_ent.data['numeros_serie_codigos']), ['PSU-001', 'PSU-002'])

        sn1 = NumeroSerie.objects.get(numero_serie='PSU-001')
        res_transf = self.client.post(
            url_movs,
            {
                'produto': self.produto.id,
                'tipo': 'TRANSFERENCIA',
                'quantidade': 1,
                'localizacao_origem': self.loc_dep.id,
                'localizacao_destino': self.loc_vit.id,
                'numeros_serie': [sn1.id],
            },
            format='json',
        )
        self.assertEqual(res_transf.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_transf.data['saldo_posterior_origem'], 1)
        self.assertEqual(res_transf.data['saldo_posterior_destino'], 1)

        # Endpoints de saldo devem refletir os saldos atuais por localização
        res_saldos = self.client.get(f"{reverse('saldos_estoque')}?produto={self.produto.id}")
        self.assertEqual(res_saldos.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_saldos.data), 2)

        # Histórico de movimentação não aceita PUT/PATCH/DELETE
        detail_url = reverse('movimentacao_estoque', kwargs={'pk': res_ent.data['id']})
        self.assertEqual(self.client.patch(detail_url, {'quantidade': 99}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
