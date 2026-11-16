from django.db.models.signals import post_save
from django.dispatch import receiver
from cadastro.models import Pessoas
from .models import EquipamentoCliente


@receiver(post_save, sender=Pessoas)
def criar_estabelecimento_novo_cliente(sender, instance, created, **kwargs):
    """
    Trigger automático: Ao cadastrar um novo cliente (tipo_pessoa 0 ou 2),
    cria automaticamente o equipamento padrão 'ESTABELECIMENTO'.
    """
    if created and instance.tipo_pessoa in (0, 2):
        EquipamentoCliente.objects.get_or_create(
            cliente=instance,
            descricao='ESTABELECIMENTO',
            defaults={
                'ativo': True,
                'observacoes': 'Equipamento padrão gerado automaticamente para atendimento no local.',
                'usuario': instance.usuario or 'SISTEMA',
            }
        )

