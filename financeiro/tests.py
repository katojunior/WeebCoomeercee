from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib import admin

from cadastro.models import Pessoas
from vendas.models import Venda
from ordem_servico.models import OrdemServico
from financeiro.models import (
    ContaBancaria, CategoriaFinanceira, TituloFinanceiro,
    ContaReceber, ContaPagar, BaixaTitulo
)


class FinanceiroTestCase(TestCase):
    def setUp(self):
        self.cliente = Pessoas.objects.create(
            razao_nome='Cliente Financeiro Teste',
            cnpj_cpf='11122233344',
            juridica_fisica=1,
            tipo_pessoa=0,
        )
        self.fornecedor = Pessoas.objects.create(
            razao_nome='Fornecedor Hardware Ltda',
            cnpj_cpf='99888777000166',
            juridica_fisica=2,
            tipo_pessoa=1,
        )
        self.caixa = ContaBancaria.objects.create(
            descricao='Caixa da Loja',
            tipo_conta='CAIXA_FISICO',
            saldo_inicial=Decimal('100.00'),
        )
        self.cat_receita = CategoriaFinanceira.objects.create(
            nome='Vendas Balcão',
            tipo='RECEITA',
        )
        self.cat_despesa = CategoriaFinanceira.objects.create(
            nome='Despesas Fornecedores',
            tipo='DESPESA',
        )

    def test_conta_bancaria_e_categoria(self):
        self.assertEqual(self.caixa.descricao, 'CAIXA DA LOJA')
        self.assertEqual(self.cat_receita.nome, 'VENDAS BALCAO')
        self.assertIn('VENDAS BALCAO', str(self.cat_receita))

    def test_conta_receber_proxy(self):
        cr = ContaReceber.objects.create(
            pessoa=self.cliente,
            categoria=self.cat_receita,
            descricao='Venda a Prazo Parcela 1/2',
            data_vencimento=date(2026, 12, 10),
            valor_original=Decimal('500.00'),
        )
        self.assertEqual(cr.tipo, 'RECEBER')
        self.assertEqual(cr.saldo_devedor, Decimal('500.00'))
        self.assertEqual(cr.status, 'ABERTO')
        self.assertEqual(ContaReceber.objects.filter(id=cr.id).count(), 1)
        self.assertEqual(ContaPagar.objects.filter(id=cr.id).count(), 0)

    def test_conta_pagar_proxy(self):
        cp = ContaPagar.objects.create(
            pessoa=self.fornecedor,
            categoria=self.cat_despesa,
            descricao='Compra de Peças NF 1234',
            data_vencimento=date(2026, 12, 20),
            valor_original=Decimal('1200.00'),
        )
        self.assertEqual(cp.tipo, 'PAGAR')
        self.assertEqual(cp.saldo_devedor, Decimal('1200.00'))
        self.assertEqual(cp.status, 'ABERTO')
        self.assertEqual(ContaPagar.objects.filter(id=cp.id).count(), 1)
        self.assertEqual(ContaReceber.objects.filter(id=cp.id).count(), 0)

    def test_baixa_parcial_e_quitacao_total(self):
        titulo = TituloFinanceiro.objects.create(
            tipo='RECEBER',
            pessoa=self.cliente,
            descricao='Honorários Manutenção',
            data_vencimento=date(2026, 12, 15),
            valor_original=Decimal('500.00'),
        )
        self.assertEqual(titulo.saldo_devedor, Decimal('500.00'))
        self.assertEqual(titulo.status, 'ABERTO')

        # 1ª Baixa parcial: R$ 200,00
        baixa1 = BaixaTitulo.objects.create(
            titulo=titulo,
            conta_bancaria=self.caixa,
            data_pagamento=date(2026, 12, 10),
            valor_pago=Decimal('200.00'),
            forma_pagamento='DINHEIRO',
        )
        titulo.refresh_from_db()
        self.assertEqual(titulo.valor_pago, Decimal('200.00'))
        self.assertEqual(titulo.saldo_devedor, Decimal('300.00'))
        self.assertEqual(titulo.status, 'PARCIAL')

        # 2ª Baixa final: R$ 300,00 (quitação)
        baixa2 = BaixaTitulo.objects.create(
            titulo=titulo,
            conta_bancaria=self.caixa,
            data_pagamento=date(2026, 12, 15),
            valor_pago=Decimal('300.00'),
            forma_pagamento='PIX',
            identificador_transacao='PIX123456789',
        )
        titulo.refresh_from_db()
        self.assertEqual(titulo.valor_pago, Decimal('500.00'))
        self.assertEqual(titulo.saldo_devedor, Decimal('0.00'))
        self.assertEqual(titulo.status, 'PAGO')

        # Estorno da 2ª baixa: exclui a baixa e verifica se o título volta para PARCIAL
        baixa2.delete()
        titulo.refresh_from_db()
        self.assertEqual(titulo.valor_pago, Decimal('200.00'))
        self.assertEqual(titulo.saldo_devedor, Decimal('300.00'))
        self.assertEqual(titulo.status, 'PARCIAL')

    def test_baixa_com_desconto_e_juros(self):
        titulo = TituloFinanceiro.objects.create(
            tipo='RECEBER',
            pessoa=self.cliente,
            descricao='Mensalidade Contrato',
            data_vencimento=date(2026, 12, 1),
            valor_original=Decimal('100.00'),
        )
        # Pagamento com R$ 10 de desconto: paga R$ 90 e quita R$ 100
        BaixaTitulo.objects.create(
            titulo=titulo,
            conta_bancaria=self.caixa,
            data_pagamento=date(2026, 12, 1),
            valor_pago=Decimal('90.00'),
            desconto=Decimal('10.00'),
            forma_pagamento='PIX',
        )
        titulo.refresh_from_db()
        self.assertEqual(titulo.valor_pago, Decimal('90.00'))
        self.assertEqual(titulo.saldo_devedor, Decimal('0.00'))
        self.assertEqual(titulo.status, 'PAGO')

    def test_admin_registrado(self):
        self.assertIn(ContaReceber, admin.site._registry)
        self.assertIn(ContaPagar, admin.site._registry)
        self.assertIn(ContaBancaria, admin.site._registry)
        self.assertIn(CategoriaFinanceira, admin.site._registry)
