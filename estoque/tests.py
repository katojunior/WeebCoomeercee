from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cadastro.models import Empresa, Pessoas
from cadastro.relatorios import consultar_resumo_cliente, executar_finalizacao_em_lote, preparar_lote_finalizacao
from cadastro_produto.models import NumeroSerie, Produtos, UnidadeMedida
from ordem_servico.models import EquipamentoCliente, ItemOrdemServico, OrdemServico
from vendas.models import ItemVenda, Venda
from .admin import MovimentacaoEstoqueAdmin, MovimentacaoEstoqueForm
from .models import MovimentacaoEstoque
from .services import registrar_movimentacao


class MovimentacaoEstoqueServiceTestCase(TestCase):
    """Testa movimentações fracionadas, com S/N, snapshots e imutabilidade no estoque único."""

    def setUp(self):
        self.fornecedor = Pessoas.objects.create(razao_nome='Fornecedor Alpha', juridica_fisica=0, tipo_pessoa=1)
        self.cliente = Pessoas.objects.create(razao_nome='Cliente Beta', juridica_fisica=1, tipo_pessoa=0)
        un_mt = UnidadeMedida.objects.get(sigla='MT')

        self.prod_fracionado = Produtos.objects.create(
            nome='Cabo de Rede Cat6',
            unidade_medida=un_mt,
            controla_numero_serie=False,
        )
        self.prod_serial = Produtos.objects.create(
            nome='SSD 1TB NVMe',
            controla_numero_serie=True,
            garantia_meses=36,
        )

    def test_fluxo_entrada_ajuste_saida_fracionado_sem_serial(self):
        mov_ent = registrar_movimentacao(
            produto=self.prod_fracionado,
            tipo='ENTRADA',
            quantidade=Decimal('10.500'),
            pessoa=self.fornecedor,
            documento_referencia='NF-100',
        )
        self.prod_fracionado.refresh_from_db()
        self.assertEqual(self.prod_fracionado.estoque_atual, Decimal('10.500'))
        self.assertEqual(mov_ent.saldo_anterior_produto, Decimal('0.000'))
        self.assertEqual(mov_ent.saldo_posterior_produto, Decimal('10.500'))

        # Ajuste negativo sem motivo deve falhar
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_fracionado,
                tipo='AJUSTE_SAIDA',
                quantidade=Decimal('1.000'),
            )

        # Saída acima do saldo disponível deve falhar em movimentação manual
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_fracionado,
                tipo='SAIDA',
                quantidade=Decimal('11.000'),
            )

        # Ajuste positivo fracionado e saída fracionada válida
        registrar_movimentacao(
            produto=self.prod_fracionado,
            tipo='AJUSTE_ENTRADA',
            quantidade=Decimal('1.250'),
            motivo='Contagem de inventario',
        )
        registrar_movimentacao(
            produto=self.prod_fracionado,
            tipo='SAIDA',
            quantidade=Decimal('3.750'),
            pessoa=self.cliente,
            documento_referencia='PED-55',
        )
        self.prod_fracionado.refresh_from_db()
        self.assertEqual(self.prod_fracionado.estoque_atual, Decimal('8.000'))

    def test_movimentacao_com_numeros_serie_e_bloqueio_fracionado(self):
        # Produto que controla S/N não aceita quantidade decimal não inteira
        with self.assertRaises(ValidationError):
            registrar_movimentacao(
                produto=self.prod_serial,
                tipo='ENTRADA',
                quantidade=Decimal('1.500'),
                numeros_serie_novos=['SN-FRAC-1'],
            )

        mov_ent = registrar_movimentacao(
            produto=self.prod_serial,
            tipo='ENTRADA',
            quantidade=Decimal('2.000'),
            numeros_serie_novos=['sn-ssd-01', 'sn-ssd-02'],
            pessoa=self.fornecedor,
            documento_referencia='NF-777',
        )
        sn1 = NumeroSerie.objects.get(numero_serie='SN-SSD-01')
        self.prod_serial.refresh_from_db()
        self.assertEqual(self.prod_serial.estoque_atual, Decimal('2.000'))
        self.assertEqual(sn1.fornecedor, self.fornecedor)
        self.assertEqual(mov_ent.numeros_serie.count(), 2)

        registrar_movimentacao(
            produto=self.prod_serial,
            tipo='SAIDA',
            quantidade=Decimal('1.000'),
            numeros_serie=[sn1],
            pessoa=self.cliente,
            documento_referencia='NF-VENDA-9',
        )
        sn1.refresh_from_db()
        self.prod_serial.refresh_from_db()
        self.assertEqual(sn1.status, 'VENDIDO')
        self.assertEqual(sn1.cliente, self.cliente)
        self.assertIsNotNone(sn1.data_fim_garantia)
        self.assertEqual(self.prod_serial.estoque_atual, Decimal('1.000'))

    def test_movimentacao_imutavel_no_model_e_admin(self):
        mov = registrar_movimentacao(
            produto=self.prod_fracionado,
            tipo='ENTRADA',
            quantidade=Decimal('3.000'),
        )
        mov.quantidade = Decimal('99.000')
        with self.assertRaises(ValidationError):
            mov.save()
        with self.assertRaises(ValidationError):
            mov.delete()

        request = RequestFactory().get('/')
        mov_admin = MovimentacaoEstoqueAdmin(MovimentacaoEstoque, AdminSite())
        self.assertFalse(mov_admin.has_change_permission(request, mov))
        self.assertFalse(mov_admin.has_delete_permission(request, mov))

        self.assertNotIn('numeros_serie_novos', mov_admin.get_fieldsets(request, mov)[1][1]['fields'])
        self.assertIn('numeros_serie_novos', mov_admin.get_fieldsets(request, None)[1][1]['fields'])

        form = MovimentacaoEstoqueForm(data={
            'produto': self.prod_serial.pk,
            'tipo': 'ENTRADA',
            'origem': 'MANUAL',
            'quantidade': '2.000',
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
                'origem': 'MANUAL',
                'quantidade': '2.000',
                'numeros_serie_novos': 'ADM-SN-01\nADM-SN-02',
            },
        )
        self.assertEqual(res_admin.status_code, 302)
        self.prod_serial.refresh_from_db()
        self.assertEqual(self.prod_serial.estoque_atual, Decimal('2.000'))
        self.assertTrue(NumeroSerie.objects.filter(numero_serie='ADM-SN-01', status='DISPONIVEL').exists())


class EstoqueAPITestCase(APITestCase):
    """Testa endpoints auditáveis de movimentações do estoque único."""

    def setUp(self):
        self.user = User.objects.create_user(username='estoquista', password='password123')
        self.client.force_authenticate(user=self.user)
        self.produto = Produtos.objects.create(nome='Fonte 650W', controla_numero_serie=True, garantia_meses=12)

    def test_movimentacao_api_entrada_saida_e_somente_leitura(self):
        url_movs = reverse('movimentacoes_estoque')
        res_ent = self.client.post(
            url_movs,
            {
                'produto': self.produto.id,
                'tipo': 'ENTRADA',
                'quantidade': '2.000',
                'numeros_serie_novos': ['PSU-001', 'PSU-002'],
                'documento_referencia': 'NF-10',
            },
            format='json',
        )
        self.assertEqual(res_ent.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ent.data['usuario'], 'estoquista')
        self.assertEqual(res_ent.data['origem'], 'MANUAL')
        self.assertEqual(Decimal(res_ent.data['saldo_anterior_produto']), Decimal('0.000'))
        self.assertEqual(Decimal(res_ent.data['saldo_posterior_produto']), Decimal('2.000'))
        self.assertEqual(sorted(res_ent.data['numeros_serie_codigos']), ['PSU-001', 'PSU-002'])

        sn1 = NumeroSerie.objects.get(numero_serie='PSU-001')
        res_saida = self.client.post(
            url_movs,
            {
                'produto': self.produto.id,
                'tipo': 'SAIDA',
                'quantidade': '1.000',
                'numeros_serie': [sn1.id],
                'documento_referencia': 'NF-SAIDA-1',
            },
            format='json',
        )
        self.assertEqual(res_saida.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res_saida.data['saldo_posterior_produto']), Decimal('1.000'))

        # Histórico de movimentação não aceita PUT/PATCH/DELETE
        detail_url = reverse('movimentacao_estoque', kwargs={'pk': res_ent.data['id']})
        self.assertEqual(self.client.patch(detail_url, {'quantidade': '99.000'}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class IntegracaoEstoqueVendasOSTestCase(TestCase):
    """Testa integração completa de baixa/estorno de estoque em Vendas, OS e Lote."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social='Kato Informatica Ltda',
            nome_fantasia='Kato Info',
            matriz=True,
            bloquear_fechamento_sem_estoque=False,
        )
        self.cliente = Pessoas.objects.create(razao_nome='Cliente Teste Estoque', juridica_fisica=1, tipo_pessoa=0)
        self.fornecedor = Pessoas.objects.create(razao_nome='Distribuidor Teste', juridica_fisica=0, tipo_pessoa=1)
        self.equipamento = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Desktop Escritório')

        self.prod_cabo = Produtos.objects.create(
            nome='Cabo Rede Cat6',
            preco_venda=Decimal('10.00'),
            controla_estoque=True,
            controla_numero_serie=False,
        )
        self.prod_servico = Produtos.objects.create(
            nome='Taxa Diagnóstico',
            preco_venda=Decimal('80.00'),
            controla_estoque=False,
            controla_numero_serie=False,
        )
        self.prod_ssd = Produtos.objects.create(
            nome='SSD Kingston 480GB',
            preco_venda=Decimal('250.00'),
            controla_estoque=True,
            controla_numero_serie=True,
            garantia_meses=24,
        )

    def test_baixa_e_estorno_fracionado_em_venda_e_os(self):
        registrar_movimentacao(
            produto=self.prod_cabo,
            tipo='ENTRADA',
            quantidade=Decimal('10.000'),
            pessoa=self.fornecedor,
        )

        # Venda consome 2.500 + item sem controle de estoque (1.000)
        venda = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        item_cabo = ItemVenda.objects.create(venda=venda, produto=self.prod_cabo, quantidade=Decimal('2.500'))
        ItemVenda.objects.create(venda=venda, produto=self.prod_servico, quantidade=Decimal('1.000'))
        venda.finalizar_venda(condicao_pagamento='PIX', quitada=True, usuario='op_teste')

        self.prod_cabo.refresh_from_db()
        item_cabo.refresh_from_db()
        self.assertEqual(self.prod_cabo.estoque_atual, Decimal('7.500'))
        self.assertIsNotNone(item_cabo.movimentacao_saida)
        self.assertEqual(item_cabo.movimentacao_saida.origem, 'VENDA')
        self.assertEqual(item_cabo.movimentacao_saida.venda, venda)
        # Item com controla_estoque=False não gera movimentação
        self.assertFalse(MovimentacaoEstoque.objects.filter(produto=self.prod_servico).exists())

        # OS consome 1.500 (PECA) e ignora serviço mesmo se vinculado a produto com estoque
        os_obj = OrdemServico.objects.create(cliente=self.cliente, equipamento=self.equipamento, status='EM_ANDAMENTO')
        item_os_peca = ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='PECA',
            produto=self.prod_cabo,
            quantidade=Decimal('1.500'),
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            produto=self.prod_cabo,
            quantidade=Decimal('5.000'),
        )
        os_obj.finalizar_os(condicao_pagamento='DINHEIRO', quitada=True, usuario='tecnico')

        self.prod_cabo.refresh_from_db()
        item_os_peca.refresh_from_db()
        self.assertEqual(self.prod_cabo.estoque_atual, Decimal('6.000'))
        self.assertEqual(item_os_peca.movimentacao_saida.origem, 'ORDEM_SERVICO')
        self.assertEqual(item_os_peca.movimentacao_saida.ordem_servico, os_obj)

        # Estornar Venda devolve 2.500 ao estoque único via movimentação inversa (ENTRADA / ESTORNO)
        venda.estornar_financeiro(usuario='admin')
        self.prod_cabo.refresh_from_db()
        item_cabo.refresh_from_db()
        self.assertEqual(self.prod_cabo.estoque_atual, Decimal('8.500'))
        self.assertIsNone(item_cabo.movimentacao_saida)
        mov_estorno = MovimentacaoEstoque.objects.filter(venda=venda, origem='ESTORNO').first()
        self.assertIsNotNone(mov_estorno)
        self.assertEqual(mov_estorno.tipo, 'ENTRADA')
        self.assertEqual(mov_estorno.quantidade, Decimal('2.500'))

    def test_venda_com_numero_serie_obrigatorio_e_estorno(self):
        registrar_movimentacao(
            produto=self.prod_ssd,
            tipo='ENTRADA',
            quantidade=Decimal('2.000'),
            numeros_serie_novos=['SSD-K-01', 'SSD-K-02'],
            pessoa=self.fornecedor,
        )
        sn1 = NumeroSerie.objects.get(numero_serie='SSD-K-01')

        venda = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        item = ItemVenda.objects.create(venda=venda, produto=self.prod_ssd, quantidade=Decimal('1.000'))

        # Sem vincular S/N no item, finalização deve ser bloqueada sem gerar títulos
        with self.assertRaises(ValidationError):
            venda.finalizar_venda(condicao_pagamento='DINHEIRO', quitada=True)
        venda.refresh_from_db()
        self.assertFalse(venda.finalizada)
        self.assertEqual(venda.titulos_financeiros.count(), 0)

        # Vinculando o S/N, finaliza baixando serial, cliente, garantia e saldo
        item.numeros_serie.add(sn1)
        venda.finalizar_venda(condicao_pagamento='DINHEIRO', quitada=True)
        sn1.refresh_from_db()
        self.prod_ssd.refresh_from_db()
        self.assertEqual(sn1.status, 'VENDIDO')
        self.assertEqual(sn1.cliente, self.cliente)
        self.assertIsNotNone(sn1.data_fim_garantia)
        self.assertEqual(self.prod_ssd.estoque_atual, Decimal('1.000'))

        # Estornar restaura S/N para DISPONIVEL e limpa dados da venda no serial
        venda.estornar_financeiro()
        sn1.refresh_from_db()
        self.prod_ssd.refresh_from_db()
        self.assertEqual(sn1.status, 'DISPONIVEL')
        self.assertIsNone(sn1.cliente)
        self.assertIsNone(sn1.data_fim_garantia)
        self.assertEqual(self.prod_ssd.estoque_atual, Decimal('2.000'))

    def test_configuracao_empresa_bloqueio_sem_estoque_inclusive_em_lote(self):
        # Com bloquear_fechamento_sem_estoque=False (padrão), permite baixar mesmo zerado (transição)
        venda_perm = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        ItemVenda.objects.create(venda=venda_perm, produto=self.prod_cabo, quantidade=Decimal('2.000'))
        venda_perm.finalizar_venda(condicao_pagamento='PIX', quitada=True)
        self.prod_cabo.refresh_from_db()
        self.assertEqual(self.prod_cabo.estoque_atual, Decimal('-2.000'))

        # Ativando bloqueio estrito na Empresa, impede venda e lote sem saldo suficiente (com rollback total)
        self.empresa.bloquear_fechamento_sem_estoque = True
        self.empresa.save(update_fields=['bloquear_fechamento_sem_estoque'])

        venda_bloq = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        ItemVenda.objects.create(venda=venda_bloq, produto=self.prod_cabo, quantidade=Decimal('1.000'))

        with self.assertRaises(ValidationError):
            venda_bloq.finalizar_venda(condicao_pagamento='PIX', quitada=True)
        venda_bloq.refresh_from_db()
        self.assertFalse(venda_bloq.finalizada)

        # Em lote: se um documento tiver produto sem saldo, todo o lote faz rollback
        os_servico_ok = OrdemServico.objects.create(cliente=self.cliente, status='EM_ANDAMENTO')
        ItemOrdemServico.objects.create(
            ordem=os_servico_ok,
            tipo_item='SERVICO',
            descricao_personalizada='Formatação',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('100.00'),
        )
        dados = consultar_resumo_cliente(
            cliente_id=self.cliente.pk,
            situacao='abertos',
            selected_keys=[f'V-{venda_bloq.id}', f'OS-{os_servico_ok.id}'],
        )
        lote = preparar_lote_finalizacao(dados)
        with self.assertRaises(ValidationError):
            executar_finalizacao_em_lote(lote, condicao_pagamento='PIX', quitada=True)

        os_servico_ok.refresh_from_db()
        self.assertFalse(os_servico_ok.finalizada)
        self.assertEqual(os_servico_ok.titulos_financeiros.count(), 0)
