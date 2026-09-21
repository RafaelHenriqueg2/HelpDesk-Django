from pathlib import Path
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Exporta dados para migrar a instalação. O arquivo contém dados privados.'

    def add_arguments(self, analisador):
        analisador.add_argument('arquivo')

    def handle(self, *args, **opcoes):
        destino = Path(opcoes['arquivo']).resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destino.open('x', encoding='utf-8') as arquivo:
                call_command('dumpdata', natural_foreign=True, natural_primary=False,
                    exclude=['contenttypes', 'auth.permission', 'sessions', 'admin.logentry'],
                    stdout=arquivo)
        except FileExistsError:
            raise CommandError('O arquivo já existe. Escolha outro nome.')
        self.stdout.write(self.style.SUCCESS('Exportação concluída. Guarde o arquivo em local privado.'))
