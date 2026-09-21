from pathlib import Path
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from chamados.models import Anexo


class Command(BaseCommand):
    help = 'Copia os anexos de uma pasta local para o storage configurado, sem excluir a origem.'

    def add_arguments(self, analisador):
        analisador.add_argument('origem')

    def handle(self, *args, **opcoes):
        origem = Path(opcoes['origem']).resolve()
        if not origem.is_dir():
            raise CommandError('Informe a pasta private_uploads da instalação original.')
        arquivos = []
        for anexo in Anexo.objects.all():
            caminho = (origem / anexo.arquivo.name).resolve()
            if not caminho.is_relative_to(origem) or not caminho.is_file():
                raise CommandError('Arquivo de origem ausente ou fora da pasta: ' + anexo.nome)
            arquivos.append((anexo, caminho))
        copiados = 0
        for anexo, caminho in arquivos:
            if default_storage.exists(anexo.arquivo.name):
                continue
            with caminho.open('rb') as entrada:
                nome = default_storage.save(anexo.arquivo.name, File(entrada))
            if nome != anexo.arquivo.name:
                default_storage.delete(nome)
                raise CommandError('Conflito de nome no destino; cópia interrompida.')
            copiados += 1
        self.stdout.write(self.style.SUCCESS(f'{copiados} anexos copiados; arquivos já existentes foram mantidos.'))
