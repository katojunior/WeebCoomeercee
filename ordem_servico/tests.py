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
        self.assertEqual(len(os_admin.inlines), 3)

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

    def test_finalizar_os_com_quitada_explicita_e_sem_conta_previa(self):
        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Servidor Dell')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            tecnico=self.tecnico,
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('300.00'),
        )
        # Finaliza em 2x no Cartão informando quitada=True (e sem nenhuma ContaBancaria pré-cadastrada)
        titulos = os_obj.finalizar_os(
            condicao_pagamento='CARTAO_CREDITO',
            numero_parcelas=2,
            intervalo_dias=30,
            desconto=Decimal('20.00'),
            quitada=True,
            numero_nf='NF-999',
            usuario='admin_user',
        )
        os_obj.refresh_from_db()
        self.assertTrue(os_obj.finalizada)
        self.assertEqual(os_obj.valor_total, Decimal('280.00'))
        self.assertEqual(len(titulos), 2)
        self.assertTrue(all(t.status == 'PAGO' for t in titulos))
        self.assertEqual(os_obj.status_financeiro, 'QUITADO')
        self.assertEqual(os_obj.total_pago_financeiro, Decimal('280.00'))

    def test_admin_finalizar_e_reabrir_os_view(self):
        from django.contrib.auth.models import User
        from django.urls import reverse

        admin_user = User.objects.create_superuser(username='super_os', password='123', email='s@s.com')
        self.client.force_login(admin_user)

        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Impressora Epson')
        os_obj = OrdemServico.objects.create(cliente=self.cliente, equipamento=eq)
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='PECA',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('250.00'),
        )

        url_fin = reverse('admin:ordem_servico_ordemservico_finalizar', args=[os_obj.pk])
        res_get = self.client.get(url_fin)
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Finalização e Faturamento da OS')

        res_post = self.client.post(url_fin, {
            'condicao_pagamento': 'CREDIARIO',
            'numero_parcelas': '3',
            'intervalo_dias': '30',
            'data_primeiro_vencimento': '2026-12-01',
            'desconto': '10.00',
            'quitada': '0',
            'numero_nf': '1234',
        })
        self.assertEqual(res_post.status_code, 302)
        os_obj.refresh_from_db()
        self.assertTrue(os_obj.finalizada)
        self.assertEqual(os_obj.status, 'FINALIZADO')
        self.assertEqual(os_obj.numero_parcelas, 3)
        self.assertEqual(os_obj.valor_total, Decimal('240.00'))
        self.assertEqual(os_obj.titulos.count(), 3)
        self.assertEqual(os_obj.status_financeiro, 'EM ABERTO')

        # Reabrir via view do botão
        url_reabrir = reverse('admin:ordem_servico_ordemservico_reabrir', args=[os_obj.pk])
        res_reabrir = self.client.get(url_reabrir)
        self.assertEqual(res_reabrir.status_code, 302)
        os_obj.refresh_from_db()
        self.assertFalse(os_obj.finalizada)
        self.assertEqual(os_obj.titulos.count(), 0)

    def test_imprimir_os_view_com_cabecalho_empresa(self):
        from django.contrib.auth.models import User
        from django.urls import reverse
        from cadastro.models import Empresa

        Empresa.objects.create(
            razao_social='Edson Heiji Kato Birigui - ME',
            nome_fantasia='Kato e Cia Informática',
            cnpj='04.831.858/0001-59',
            inscricao_estadual='214.138.526-118',
            endereco='Rua Gonçalo Ibanhes',
            numero='484A',
            bairro='Centro',
            cep='16200-192',
            telefone='(18) 3642-1088',
            chave_pix='04.831.858/0001-59',
            texto_rodape_impressao='Garantia de 90 dias nos serviços prestados.',
            matriz=True,
        )

        admin_user = User.objects.create_superuser(username='super_print_os', password='123', email='po@s.com')
        self.client.force_login(admin_user)

        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='Notebook Acer Nitro', numero_serie='SN-ACER-01')
        os_obj = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            tecnico=self.tecnico,
            defeito_reclamado='Superaquecimento',
            laudo_tecnico='Troca de pasta térmica e limpeza de cooler',
        )
        ItemOrdemServico.objects.create(
            ordem=os_obj,
            tipo_item='SERVICO',
            descricao_personalizada='Limpeza Preventiva Completa',
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('120.00'),
        )
        os_obj.finalizar_os(condicao_pagamento='PIX', numero_parcelas=1, quitada=True)

        url_print = reverse('admin:ordem_servico_ordemservico_imprimir', args=[os_obj.pk])
        res = self.client.get(url_print)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'KATO E CIA INFORMATICA')
        self.assertContains(res, '04.831.858/0001-59')
        self.assertContains(res, 'NOTEBOOK ACER NITRO')
        self.assertContains(res, 'SUPERAQUECIMENTO')
        self.assertContains(res, 'TROCA DE PASTA TERMICA E LIMPEZA DE COOLER')
        self.assertContains(res, 'Garantia de 90 dias nos serviços prestados.')
        self.assertContains(res, 'mode-2vias')

    def test_range_filter_data_abertura_changelist(self):
        from datetime import datetime
        from django.contrib.auth.models import User
        from django.urls import reverse
        from django.utils import timezone

        admin_user = User.objects.create_superuser(username='super_drf_os', password='123', email='do@s.com')
        self.client.force_login(admin_user)

        eq = EquipamentoCliente.objects.create(cliente=self.cliente, descricao='PC Teste Range')
        tz = timezone.get_current_timezone()
        os1 = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            status='ORCAMENTO',
            data_abertura=timezone.make_aware(datetime(2026, 9, 15, 9, 0), tz),
        )
        os2 = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            status='EM_ANDAMENTO',
            data_abertura=timezone.make_aware(datetime(2026, 11, 5, 22, 45), tz),
        )
        os3 = OrdemServico.objects.create(
            cliente=self.cliente,
            equipamento=eq,
            status='FINALIZADO',
            data_abertura=timezone.make_aware(datetime(2026, 11, 18, 14, 0), tz),
        )

        url = reverse('admin:ordem_servico_ordemservico_changelist')

        res_base = self.client.get(url)
        self.assertEqual(res_base.status_code, 200)
        self.assertContains(res_base, 'data_abertura__range_start')
        self.assertContains(res_base, 'data_abertura__range_end')

        res_range = self.client.get(url, {
            'data_abertura__range_start': '2026-11-01',
            'data_abertura__range_end': '2026-11-05',
        })
        self.assertEqual(res_range.status_code, 200)
        self.assertEqual(list(res_range.context['cl'].queryset.values_list('id', flat=True)), [os2.id])

        # Filtra somente com data final preenchida
        res_until = self.client.get(url, {
            'data_abertura__range_end': '2026-10-01',
        })
        self.assertEqual(res_until.status_code, 200)
        self.assertEqual(list(res_until.context['cl'].queryset.values_list('id', flat=True)), [os1.id])

        # Verifica facets na listagem de OS
        res_facets = self.client.get(url, {'_facets': 'True'})
        self.assertEqual(res_facets.status_code, 200)

        # Confirma que os3 está fora do filtro anterior e aparece na listagem geral
        res_all = self.client.get(url)
        self.assertIn(os3.id, list(res_all.context['cl'].queryset.values_list('id', flat=True)))

        # Garante que a tela de cadastro de nova OS (/add/) renderiza sem TypeError no format_html
        res_add = self.client.get(reverse('admin:ordem_servico_ordemservico_add'))
        self.assertEqual(res_add.status_code, 200)
        self.assertContains(res_add, 'Finalizar / Faturar OS')


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
