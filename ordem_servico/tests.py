import os
from decimal import Decimal
from io import StringIO
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.contrib import admin

from cadastro.models import Pessoas
from cadastro_produto.models import Produtos
from .models import EquipamentoCliente, OrdemServico, ItemOrdemServico


class OrdemServicoModelTestCase(TestCase):
    def setUp(self):
        self.cliente = Pessoas.objects.create(
            razao_nome='Cliente Teste OS',
            juridica_fisica=1,
            tipo_pessoa=0
        )
        self.tecnico = Pessoas.objects.create(
            razao_nome='Tecnico Responsavel',
            juridica_fisica=1,
            tipo_pessoa=0,
            funcionario=True
        )
        self.produto = Produtos.objects.create(
            nome='SSD Kingston 480GB',
            preco_custo=Decimal('120.00'),
            preco_venda=Decimal('180.00')
        )

    def test_criar_equipamento_cliente(self):
        eq = EquipamentoCliente.objects.create(
            cliente=self.cliente,
            descricao='notebook dell vostro 3500',
            numero_serie='sn123456'
        )
        self.assertEqual(eq.descricao, 'NOTEBOOK DELL VOSTRO 3500')
        self.assertEqual(eq.numero_serie, 'SN123456')
        self.assertTrue(eq.ativo)
        self.assertIn('NOTEBOOK DELL VOSTRO 3500', str(eq))
        self.assertIn('SN123456', str(eq))

    def test_criar_ordem_servico_e_itens(self):
        eq = EquipamentoCliente.objects.create(
            cliente=self.cliente,
            descricao='Desktop Gamer'
        )
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            tecnico=self.tecnico,
            status='EM_ANDAMENTO',
            defeito_reclamado='Computador lento',
            laudo_tecnico='Instalado SSD e formatado'
        )
        self.assertEqual(os_obj.status, 'EM_ANDAMENTO')
        self.assertEqual(os_obj.get_status_display(), 'Em Andamento')
        self.assertEqual(os_obj.tecnico, self.tecnico)

        item = ItemOrdemServico.objects.create(
            ordem=os_obj,
            equipamento=eq,
            produto=self.produto,
            tipo_item='PECA',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('180.00')
        )
        self.assertEqual(item.valor_total, Decimal('180.00'))
        self.assertEqual(os_obj.itens.count(), 1)

    def test_bloqueio_os_finalizada(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Impressora HP')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            status='FINALIZADO',
            finalizada=True
        )
        os_admin = admin.site._registry[OrdemServico]
        readonly = os_admin.get_readonly_fields(None, os_obj)
        self.assertIn('status', readonly)
        self.assertIn('cliente', readonly)
        self.assertIn('valor_total', readonly)

        inline = os_admin.inlines[0](OrdemServico, admin.site)
        self.assertFalse(inline.has_add_permission(None, os_obj))
        self.assertFalse(inline.has_change_permission(None, os_obj))
        self.assertFalse(inline.has_delete_permission(None, os_obj))

    def test_equipamento_str_sem_nome_cliente(self):
        eq = EquipamentoCliente.objects.create(
            cliente=self.cliente,
            descricao='Notebook Lenovo - Branco',
            numero_serie='SN9988'
        )
        # O nome do cliente NÃO deve mais aparecer no __str__
        self.assertEqual(str(eq), 'NOTEBOOK LENOVO - BRANCO (S/N: SN9988)')
        self.assertNotIn(self.cliente.razao_nome, str(eq))

    def test_defeito_e_laudo_unidecode_upper(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='PC Balcão')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            defeito_reclamado='computador não liga, tela azul com ruído',
            laudo_tecnico='trocado capacitor da placa-mãe e limpeza'
        )
        self.assertEqual(os_obj.defeito_reclamado, 'COMPUTADOR NAO LIGA, TELA AZUL COM RUIDO')
        self.assertEqual(os_obj.laudo_tecnico, 'TROCADO CAPACITOR DA PLACA-MAE E LIMPEZA')

    def test_calculo_automatico_totais_os_e_itens(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Desktop')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            desconto=Decimal('20.00')
        )
        # Item Peça: 2 x 150.00 = 300.00
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='PECA',
            quantidade=Decimal('2.000'),
            valor_unitario=Decimal('150.00')
        )
        # Item Serviço: 1 x 80.00 = 80.00
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('80.00')
        )
        os_obj.refresh_from_db()
        self.assertEqual(os_obj.valor_pecas, Decimal('300.00'))
        self.assertEqual(os_obj.valor_servicos, Decimal('80.00'))
        # Total = 300 + 80 - 20 (desconto) = 360.00
        self.assertEqual(os_obj.valor_total, Decimal('360.00'))

    def test_tecnico_apenas_funcionarios_admin(self):
        # Cria pessoa que NÃO é funcionário
        Pessoas.objects.create(
            razao_nome='Cliente Comum Nao Funcionario',
            juridica_fisica=1,
            tipo_pessoa=0,
            funcionario=False
        )
        os_admin = admin.site._registry[OrdemServico]
        formfield = os_admin.formfield_for_foreignkey(
            OrdemServico._meta.get_field('tecnico'),
            request=None
        )
        qs_ids = list(formfield.queryset.values_list('id', flat=True))
        self.assertIn(self.tecnico.id, qs_ids)
        # Verifica que todos na listagem são funcionários
        self.assertTrue(all(p.funcionario for p in formfield.queryset))

    def test_admin_inlines_count(self):
        os_admin = admin.site._registry[OrdemServico]
        self.assertEqual(len(os_admin.inlines), 2)

    def test_gerar_financeiro_os_avista(self):
        from financeiro.models import ContaBancaria
        caixa = ContaBancaria.objects.create(
            descricao='Caixa Teste OS',
            tipo_conta='CAIXA_FISICO',
            saldo_inicial=Decimal('0.00')
        )
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Notebook Asus')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            tecnico=self.tecnico,
            condicao_pagamento='PIX',
            conta_destino=caixa,
            numero_parcelas=1
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='PECA',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('150.00')
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('50.00')
        )
        titulos = os_obj.gerar_financeiro(usuario='tester')
        self.assertEqual(len(titulos), 1)
        tit = titulos[0]
        self.assertTrue(os_obj.finalizada)
        self.assertEqual(os_obj.status, 'FINALIZADO')
        self.assertEqual(tit.status, 'PAGO')
        self.assertEqual(tit.valor_original, Decimal('200.00'))
        self.assertEqual(tit.valor_pago, Decimal('200.00'))
        self.assertEqual(tit.saldo_devedor, Decimal('0.00'))
        self.assertEqual(tit.baixas.count(), 1)
        self.assertEqual(os_obj.status_financeiro, 'QUITADO')
        self.assertEqual(os_obj.total_pago_financeiro, Decimal('200.00'))
        self.assertEqual(os_obj.total_pendente_financeiro, Decimal('0.00'))

    def test_gerar_financeiro_os_parcelado_com_residuo(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='PC Dell')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            condicao_pagamento='BOLETO',
            numero_parcelas=3,
            intervalo_dias=30
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('100.00')
        )
        titulos = os_obj.gerar_financeiro(usuario='tester')
        self.assertEqual(len(titulos), 3)
        vals = [t.valor_original for t in titulos]
        self.assertEqual(vals, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])
        self.assertEqual(sum(vals), Decimal('100.00'))
        self.assertTrue(all(t.status == 'ABERTO' for t in titulos))
        self.assertEqual(os_obj.status_financeiro, 'EM ABERTO')
        self.assertEqual(os_obj.total_pendente_financeiro, Decimal('100.00'))

    def test_estornar_financeiro_reabre_os(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='PC Lenovo')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            condicao_pagamento='BOLETO',
            numero_parcelas=2
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='PECA',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('75.00')
        )
        os_obj.gerar_financeiro(usuario='tester')
        self.assertTrue(os_obj.finalizada)
        self.assertEqual(os_obj.titulos.count(), 2)

        os_obj.estornar_financeiro(usuario='tester')
        self.assertFalse(os_obj.finalizada)
        self.assertEqual(os_obj.status, 'ORCAMENTO')
        self.assertIsNone(os_obj.data_finalizacao)
        self.assertEqual(os_obj.titulos.count(), 0)
        self.assertEqual(os_obj.status_financeiro, 'SEM TITULOS')


class ImportarOsFirebirdTestCase(TestCase):
    def test_importar_os_firebird_arquivo_inexistente(self):
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('importar_os_firebird', arquivo='arquivo_fantasma.fdb', stdout=out)
        self.assertIn('Arquivo Firebird não encontrado', str(ctx.exception))

    def test_importar_os_firebird_dry_run_execucao(self):
        fdb_path = os.path.join(settings.BASE_DIR, 'INFYSK-ATUAL.FDB')
        if not os.path.exists(fdb_path):
            self.skipTest('Arquivo INFYSK-ATUAL.FDB não encontrado no ambiente de teste.')

        out = StringIO()
        call_command('importar_os_firebird', arquivo=fdb_path, dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn('MODO DRY-RUN ATIVADO', output)
        self.assertIn('Simulação concluída com sucesso', output)
