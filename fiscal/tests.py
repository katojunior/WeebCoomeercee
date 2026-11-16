from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Cest, Cfop, Ncm


class FiscalModelsTestCase(TestCase):
    """Testa carga inicial das tabelas fiscais e validação/normalização de códigos."""

    def test_carga_inicial_ncm_cest_cfop_via_migration(self):
        self.assertGreaterEqual(Cfop.objects.count(), 15)
        self.assertGreaterEqual(Ncm.objects.count(), 15)
        self.assertGreaterEqual(Cest.objects.count(), 8)
        self.assertEqual(Cfop.objects.get(codigo='5102').tipo_operacao, 'SAIDA')
        self.assertEqual(Cfop.objects.get(codigo='1102').tipo_operacao, 'ENTRADA')

    def test_normalizacao_e_validacao_codigos_fiscais(self):
        ncm = Ncm(codigo='8518.30.00', descricao='Fones de ouvido e auriculares')
        ncm.full_clean()
        ncm.save()
        self.assertEqual(ncm.codigo, '85183000')
        self.assertEqual(ncm.codigo_formatado, '8518.30.00')
        self.assertEqual(ncm.descricao, 'FONES DE OUVIDO E AURICULARES')

        cest = Cest(codigo='21.057.00', descricao='Fones de ouvido')
        cest.full_clean()
        cest.save()
        self.assertEqual(cest.codigo, '2105700')
        self.assertEqual(cest.codigo_formatado, '21.057.00')

        with self.assertRaises(ValidationError):
            Ncm(codigo='1234', descricao='Curto').full_clean()

        with self.assertRaises(ValidationError):
            Cest(codigo='210570', descricao='Curto').full_clean()

        with self.assertRaises(ValidationError):
            Cfop(codigo='9102', descricao='Prefixo invalido').full_clean()


class FiscalAPITestCase(APITestCase):
    """Testa endpoints REST de NCM, CEST e CFOP."""

    def setUp(self):
        self.user = User.objects.create_user(username='fiscal_user', password='password123')
        self.client.force_authenticate(user=self.user)

    def test_crud_fiscal_endpoints(self):
        res_ncm = self.client.post(
            reverse('ncms'),
            {'codigo': '8523.51.10', 'descricao': 'Cartoes de memoria flash'},
            format='json',
        )
        self.assertEqual(res_ncm.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ncm.data['codigo'], '85235110')
        self.assertEqual(res_ncm.data['codigo_formatado'], '8523.51.10')

        res_cest = self.client.post(
            reverse('cests'),
            {'codigo': '21.053.00', 'descricao': 'Cartoes de memoria'},
            format='json',
        )
        self.assertEqual(res_cest.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_cest.data['codigo'], '2105300')

        res_cfop = self.client.post(
            reverse('cfops'),
            {'codigo': '5922', 'descricao': 'Lancamento simples faturamento', 'tipo_operacao': 'SAIDA', 'movimenta_estoque': False},
            format='json',
        )
        self.assertEqual(res_cfop.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_cfop.data['tipo_operacao_display'], 'Saída')

        res_bad = self.client.post(
            reverse('ncms'),
            {'codigo': '8523ABCD', 'descricao': 'Invalido'},
            format='json',
        )
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)
