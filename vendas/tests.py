from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib import admin

from cadastro.models import Pessoas
from cadastro_produto.models import Produtos
from vendas.models import Venda, ItemVenda
from vendas.admin import VendaAdmin, ItemVendaAdmin


class VendasTestCase(TestCase):
    def setUp(self):
        self.cliente = Pessoas.objects.create(
            razao_nome='Cliente Teste Vendas',
            cnpj_cpf='12345678901',
            juridica_fisica=1,
            tipo_pessoa=0,
        )
        self.vendedor = Pessoas.objects.create(
            razao_nome='Vendedor Balcão',
            juridica_fisica=1,
            tipo_pessoa=0,
            funcionario=True,
        )
        self.produto_a = Produtos.objects.create(
            nome='Teclado USB Gamer',
            preco_custo=Decimal('50.00'),
            preco_venda=Decimal('90.00'),
        )
        self.produto_b = Produtos.objects.create(
            nome='Mouse Óptico USB',
            preco_custo=Decimal('20.00'),
            preco_venda=Decimal('40.00'),
        )

    def test_criar_venda_simples(self):
        venda = Venda.objects.create(
            cliente=self.cliente,
            vendedor=self.vendedor,
            status='FINALIZADO',
            subtotal=Decimal('130.00'),
            desconto=Decimal('10.00'),
            valor_total=Decimal('120.00'),
            forma_pagamento='Dinheiro: R$ 120.00',
            numero_nf='000123',
        )
        self.assertEqual(venda.status, 'FINALIZADO')
        self.assertEqual(venda.get_status_display(), 'Finalizado')
        self.assertEqual(venda.valor_total, Decimal('120.00'))
        self.assertIn('Venda #', str(venda))
        self.assertIn('CLIENTE TESTE VENDAS', str(venda))

    def test_venda_consumidor_sem_cliente(self):
        venda = Venda.objects.create(
            cliente=None,
            status='FINALIZADO',
            valor_total=Decimal('50.00'),
        )
        self.assertIsNone(venda.cliente)
        self.assertIn('Consumidor / Balcão', str(venda))

    def test_item_venda_calculo_automatico(self):
        venda = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        item1 = ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            sequencia=1,
            quantidade=Decimal('2.000'),
            valor_unitario=Decimal('90.00'),
        )
        self.assertEqual(item1.valor_total, Decimal('180.00'))
        self.assertIn('2.000x TECLADO USB GAMER', str(item1))

        item2 = ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_b,
            sequencia=2,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('40.00'),
            desconto_unitario=Decimal('5.00'),
        )
        self.assertEqual(item2.valor_total, Decimal('35.00'))

        venda.desconto = Decimal('15.00')
        total = venda.calcular_totais()
        self.assertEqual(venda.subtotal, Decimal('215.00'))
        self.assertEqual(total, Decimal('200.00'))
        self.assertEqual(venda.valor_total, Decimal('200.00'))

    def test_cascata_deletar_venda_deleta_itens(self):
        venda = Venda.objects.create(cliente=self.cliente, status='ORCAMENTO')
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('90.00'),
            valor_total=Decimal('90.00'),
        )
        self.assertEqual(ItemVenda.objects.filter(venda=venda).count(), 1)
        venda_id = venda.id
        venda.delete()
        self.assertEqual(ItemVenda.objects.filter(venda_id=venda_id).count(), 0)

    def test_bloqueio_venda_finalizada(self):
        venda = Venda.objects.create(cliente=self.cliente, status='FINALIZADO', finalizada=True)
        venda_admin = admin.site._registry[Venda]
        readonly = venda_admin.get_readonly_fields(None, venda)
        self.assertIn('status', readonly)
        self.assertIn('cliente', readonly)
        self.assertIn('valor_total', readonly)

        inline = venda_admin.inlines[0](Venda, admin.site)
        self.assertFalse(inline.has_add_permission(None, venda))
        self.assertFalse(inline.has_change_permission(None, venda))
        self.assertFalse(inline.has_delete_permission(None, venda))

    def test_admin_configuracao(self):
        self.assertIn(Venda, admin.site._registry)
        self.assertIn(ItemVenda, admin.site._registry)

        venda_admin = admin.site._registry[Venda]
        self.assertIn('cliente__razao_nome', venda_admin.search_fields)
        self.assertIn('status', venda_admin.list_filter)
        self.assertEqual(len(venda_admin.inlines), 2)

    def test_gerar_financeiro_avista(self):
        from financeiro.models import ContaBancaria
        caixa = ContaBancaria.objects.create(
            descricao='Caixa Teste Venda',
            tipo_conta='CAIXA_FISICO',
            saldo_inicial=Decimal('0.00')
        )
        venda = Venda.objects.create(
            cliente=self.cliente,
            vendedor=self.vendedor,
            condicao_pagamento='DINHEIRO',
            conta_destino=caixa,
            numero_parcelas=1,
            data_primeiro_vencimento=timezone.localdate()
        )
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('150.00'),
            valor_total=Decimal('150.00')
        )
        titulos = venda.gerar_financeiro(usuario='tester')
        self.assertEqual(len(titulos), 1)
        tit = titulos[0]
        self.assertTrue(venda.finalizada)
        self.assertEqual(venda.status, 'FINALIZADO')
        self.assertEqual(tit.status, 'PAGO')
        self.assertEqual(tit.valor_original, Decimal('150.00'))
        self.assertEqual(tit.valor_pago, Decimal('150.00'))
        self.assertEqual(tit.saldo_devedor, Decimal('0.00'))
        self.assertEqual(tit.baixas.count(), 1)
        self.assertEqual(venda.status_financeiro, 'QUITADO')
        self.assertEqual(venda.total_pago_financeiro, Decimal('150.00'))
        self.assertEqual(venda.total_pendente_financeiro, Decimal('0.00'))

    def test_gerar_financeiro_parcelado_com_residuo(self):
        venda = Venda.objects.create(
            cliente=self.cliente,
            condicao_pagamento='BOLETO',
            numero_parcelas=3,
            intervalo_dias=30,
            data_primeiro_vencimento=timezone.localdate()
        )
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('100.00'),
            valor_total=Decimal('100.00')
        )
        titulos = venda.gerar_financeiro(usuario='tester')
        self.assertEqual(len(titulos), 3)
        vals = [t.valor_original for t in titulos]
        self.assertEqual(vals, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])
        self.assertEqual(sum(vals), Decimal('100.00'))
        self.assertTrue(all(t.status == 'ABERTO' for t in titulos))
        self.assertEqual(venda.status_financeiro, 'EM ABERTO')
        self.assertEqual(venda.total_pendente_financeiro, Decimal('100.00'))

    def test_estornar_financeiro_reabre_venda(self):
        venda = Venda.objects.create(
            cliente=self.cliente,
            condicao_pagamento='BOLETO',
            numero_parcelas=2
        )
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('50.00'),
            valor_total=Decimal('50.00')
        )
        venda.gerar_financeiro(usuario='tester')
        self.assertTrue(venda.finalizada)
        self.assertEqual(venda.titulos.count(), 2)

        venda.estornar_financeiro(usuario='tester')
        self.assertFalse(venda.finalizada)
        self.assertEqual(venda.status, 'ABERTO')
        self.assertIsNone(venda.data_finalizacao)
        self.assertEqual(venda.titulos.count(), 0)
        self.assertEqual(venda.status_financeiro, 'SEM TITULOS')
