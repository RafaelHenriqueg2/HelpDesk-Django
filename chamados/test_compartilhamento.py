import importlib.util
import io
import json
import tempfile
from pathlib import Path
from unittest import skipUnless
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from .models import Usuario, Categoria


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TestesCompartilhamento(TestCase):
    def test_export_preserves_user_uuid_and_never_overwrites(self):
        usuario = Usuario.objects.create_user('export@test.local', 'Export!904', nome='Exportação')
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'dados.backup.json'
            call_command('exportar_dados', str(caminho), stdout=io.StringIO())
            dados = json.loads(caminho.read_text(encoding='utf-8'))
            usuarios = [item for item in dados if item['model'] == 'chamados.usuario']
            self.assertEqual(usuarios[0]['pk'], str(usuario.pk))
            with self.assertRaises(CommandError):
                call_command('exportar_dados', str(caminho), stdout=io.StringIO())

    def test_import_refuses_existing_accounts(self):
        Usuario.objects.create_user('exists@test.local', 'Exists!904', nome='Existente')
        with self.assertRaisesMessage(CommandError, 'O destino contém usuários'):
            call_command('importar_dados', 'nao_existe.json', stdout=io.StringIO())

    def test_import_refuses_custom_categories(self):
        Categoria.objects.create(nome='Categoria local que deve permanecer')
        with self.assertRaisesMessage(CommandError, 'categorias personalizadas'):
            call_command('importar_dados', 'nao_existe.json', stdout=io.StringIO())

    @skipUnless(importlib.util.find_spec('storages'), 'Requer requirements-cloud.txt')
    def test_cloud_storage_does_not_publish_urls(self):
        from .storage import ArmazenamentoPrivadoS3
        armazenamento = ArmazenamentoPrivadoS3(access_key='test', secret_key='test',
            bucket_name='test', endpoint_url='https://example.invalid')
        with self.assertRaises(NotImplementedError):
            armazenamento.url('anexos/teste.pdf')
