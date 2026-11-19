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

    def test_item_venda_preenche_preco_padrao_mas_permite_edicao(self):
        venda = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        # Sem informar valor_unitario -> assume preco_venda (90.00)
        item_padrao = ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('2.000'),
        )
        self.assertEqual(item_padrao.valor_unitario, Decimal('90.00'))
        self.assertEqual(item_padrao.valor_total, Decimal('180.00'))

        # Informando valor_unitario editado (75.00) -> respeita o valor informado
        item_editado = ItemVenda.objects.create(
            venda=venda,
            produto=self.produto_a,
            quantidade=Decimal('1.000'),
            valor_unitario=Decimal('75.00'),
        )
        self.assertEqual(item_editado.valor_unitario, Decimal('75.00'))
        self.assertEqual(item_editado.valor_total, Decimal('75.00'))

    def test_vendedor_apenas_funcionarios_no_admin(self):
        venda_admin = admin.site._registry[Venda]
        formfield = venda_admin.formfield_for_foreignkey(
            Venda._meta.get_field('vendedor'),
            request=None,
        )
        qs_ids = list(formfield.queryset.values_list('id', flat=True))
        self.assertIn(self.vendedor.id, qs_ids)
        self.assertNotIn(self.cliente.id, qs_ids)
        self.assertTrue(all(p.funcionario for p in formfield.queryset))

    def test_venda_sem_cliente_quitada_usa_consumidor_final_e_bloqueia_aprazo(self):
        from django.core.exceptions import ValidationError

        venda_aprazo = Venda.objects.create(cliente=None, status='ABERTO')
        ItemVenda.objects.create(venda=venda_aprazo, produto=self.produto_a, quantidade=Decimal('1.000'))
        with self.assertRaises(ValidationError):
            venda_aprazo.finalizar_venda(condicao_pagamento='CREDIARIO', numero_parcelas=2, quitada=False)

        venda_avista = Venda.objects.create(cliente=None, status='ABERTO')
        ItemVenda.objects.create(venda=venda_avista, produto=self.produto_a, quantidade=Decimal('1.000'))
        titulos = venda_avista.finalizar_venda(condicao_pagamento='PIX', numero_parcelas=1, quitada=True)
        self.assertEqual(len(titulos), 1)
        self.assertEqual(titulos[0].pessoa.razao_nome, 'CONSUMIDOR FINAL')
        self.assertEqual(titulos[0].status, 'PAGO')

    def test_atualiza_primeira_e_ultima_compra_cliente_ao_finalizar(self):
        self.assertIsNone(self.cliente.primeira_compra)
        self.assertIsNone(self.cliente.ultima_compra)

        venda = Venda.objects.create(cliente=self.cliente, status='ABERTO')
        ItemVenda.objects.create(venda=venda, produto=self.produto_b, quantidade=Decimal('1.000'))
        venda.finalizar_venda(condicao_pagamento='DINHEIRO', numero_parcelas=1, quitada=True)

        self.cliente.refresh_from_db()
        self.assertIsNotNone(self.cliente.primeira_compra)
        self.assertEqual(self.cliente.primeira_compra, self.cliente.ultima_compra)

    def test_admin_finalizar_reabrir_e_preco_produto_views(self):
        from django.contrib.auth.models import User
        from django.urls import reverse

        admin_user = User.objects.create_superuser(username='super_vnd', password='123', email='v@v.com')
        self.client.force_login(admin_user)

        url_preco = reverse('admin:vendas_venda_preco_produto', args=[self.produto_a.pk])
        res_preco = self.client.get(url_preco)
        self.assertEqual(res_preco.status_code, 200)
        self.assertEqual(res_preco.json()['preco_venda'], '90.00')

        venda = Venda.objects.create(cliente=self.cliente, vendedor=self.vendedor, status='ABERTO')
        ItemVenda.objects.create(venda=venda, produto=self.produto_a, quantidade=Decimal('2.000'))

        url_fin = reverse('admin:vendas_venda_finalizar', args=[venda.pk])
        res_get = self.client.get(url_fin)
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Finalização e Faturamento da Venda')

        res_post = self.client.post(url_fin, {
            'condicao_pagamento': 'CARTAO_CREDITO',
            'numero_parcelas': '2',
            'intervalo_dias': '30',
            'data_primeiro_vencimento': '2026-12-10',
            'desconto': '20.00',
            'quitada': '0',
            'numero_nf': 'NF-555',
        })
        self.assertEqual(res_post.status_code, 302)
        venda.refresh_from_db()
        self.assertTrue(venda.finalizada)
        self.assertEqual(venda.valor_total, Decimal('160.00'))
        self.assertEqual(venda.titulos.count(), 2)
        self.assertEqual(venda.status_financeiro, 'EM ABERTO')

        url_reabrir = reverse('admin:vendas_venda_reabrir', args=[venda.pk])
        res_reabrir = self.client.get(url_reabrir)
        self.assertEqual(res_reabrir.status_code, 302)
        venda.refresh_from_db()
        self.assertFalse(venda.finalizada)
        self.assertEqual(venda.titulos.count(), 0)

    def test_imprimir_venda_view_com_cabecalho_empresa(self):
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
            texto_rodape_impressao='Garantia legal de 90 dias contra defeitos de fabricação.',
            matriz=True,
        )

        admin_user = User.objects.create_superuser(username='super_print', password='123', email='p@p.com')
        self.client.force_login(admin_user)

        venda = Venda.objects.create(cliente=self.cliente, vendedor=self.vendedor, status='ABERTO')
        ItemVenda.objects.create(venda=venda, produto=self.produto_a, quantidade=Decimal('2.000'))
        venda.finalizar_venda(condicao_pagamento='PIX', numero_parcelas=1, quitada=True)

        url_print = reverse('admin:vendas_venda_imprimir', args=[venda.pk])
        res = self.client.get(url_print)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'KATO E CIA INFORMATICA')
        self.assertContains(res, '04.831.858/0001-59')
        self.assertContains(res, 'TECLADO USB GAMER')
        self.assertContains(res, 'CLIENTE TESTE VENDAS')
        self.assertContains(res, 'Garantia legal de 90 dias')
        self.assertContains(res, 'mode-2vias')

    def test_range_filter_data_venda_changelist(self):
        from datetime import datetime, time
        from django.contrib.auth.models import User
        from django.urls import reverse

        admin_user = User.objects.create_superuser(username='super_drf_v', password='123', email='dv@v.com')
        self.client.force_login(admin_user)

        tz = timezone.get_current_timezone()
        v1 = Venda.objects.create(
            cliente=self.cliente,
            status='ABERTO',
            data_venda=timezone.make_aware(datetime(2026, 10, 5, 10, 0), tz),
            valor_total=Decimal('10.00'),
        )
        v2 = Venda.objects.create(
            cliente=self.cliente,
            status='FINALIZADO',
            data_venda=timezone.make_aware(datetime(2026, 11, 10, 23, 50), tz),
            valor_total=Decimal('20.00'),
        )
        v3 = Venda.objects.create(
            cliente=self.cliente,
            status='FINALIZADO',
            data_venda=timezone.make_aware(datetime(2026, 11, 20, 8, 30), tz),
            valor_total=Decimal('30.00'),
        )

        url = reverse('admin:vendas_venda_changelist')

        # Renderiza campos De / Até e atalhos rápidos
        res_base = self.client.get(url)
        self.assertEqual(res_base.status_code, 200)
        self.assertContains(res_base, 'data_venda__range_start')
        self.assertContains(res_base, 'data_venda__range_end')
        self.assertContains(res_base, 'Mês passado')

        # Filtra intervalo incluindo o final do dia 2026-11-10 (23:50)
        res_range = self.client.get(url, {
            'data_venda__range_start': '2026-11-01',
            'data_venda__range_end': '2026-11-10',
        })
        self.assertEqual(res_range.status_code, 200)
        qs = list(res_range.context['cl'].queryset.values_list('id', flat=True))
        self.assertEqual(qs, [v2.id])

        # Filtra somente data inicial (aberta no fim) combinada com status='FINALIZADO'
        res_open_end = self.client.get(url, {
            'data_venda__range_start': '2026-11-01',
            'status__exact': 'FINALIZADO',
        })
        self.assertEqual(res_open_end.status_code, 200)
        qs_open_end = set(res_open_end.context['cl'].queryset.values_list('id', flat=True))
        self.assertEqual(qs_open_end, {v2.id, v3.id})

        # Verifica contagem com facets ativados
        res_facets = self.client.get(url, {'_facets': 'True'})
        self.assertEqual(res_facets.status_code, 200)

        # Datas invertidas continuam funcionando sem erro
        res_inverted = self.client.get(url, {
            'data_venda__range_start': '2026-10-10',
            'data_venda__range_end': '2026-10-01',
        })
        self.assertEqual(res_inverted.status_code, 200)
        self.assertEqual(list(res_inverted.context['cl'].queryset.values_list('id', flat=True)), [v1.id])

        # Garante que a tela de cadastro de nova Venda (/add/) renderiza sem TypeError no format_html
        res_add = self.client.get(reverse('admin:vendas_venda_add'))
        self.assertEqual(res_add.status_code, 200)
        self.assertContains(res_add, 'Finalizar / Faturar Venda')
