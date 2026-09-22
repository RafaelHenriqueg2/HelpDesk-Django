from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from chamados.models import Usuario, Chamado, Categoria


class Command(BaseCommand):
    help = 'Importa dados somente em uma instalação sem usuários e chamados.'

    def add_arguments(self, analisador):
        analisador.add_argument('arquivo')

    @transaction.atomic
    def handle(self, *args, **opcoes):
        if Usuario.objects.exists() or Chamado.objects.exists():
            raise CommandError('O destino contém usuários ou chamados; importação cancelada.')
        if Categoria.objects.exclude(nome__in=['Acesso', 'Computador', 'Impressora', 'Internet', 'Sistemas', 'Outros']).exists():
            raise CommandError('O destino contém categorias personalizadas; use uma instalação vazia.')
        # Apenas as categorias sem vínculos criadas pela migration inicial.
        Categoria.objects.all().delete()
        call_command('loaddata', opcoes['arquivo'], verbosity=0)
        self.stdout.write(self.style.SUCCESS('Dados importados, incluindo os anexos armazenados no banco.'))
