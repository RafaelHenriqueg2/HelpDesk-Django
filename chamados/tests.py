import io
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

import jwt
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Usuario, Chamado, Anexo, RegistroLogin, HistoricoStatus
from .forms import FormularioChamado
from . import services


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TestesHelpDesk(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.senha = 'TesteSeguro!4827'
        cls.usuario = Usuario.objects.create_user('ana@example.com', cls.senha, nome='Ana Silva')
        cls.outra_pessoa = Usuario.objects.create_user('bia@example.com', cls.senha, nome='Bia Costa')
        cls.admin = Usuario.objects.create_superuser('admin@example.com', cls.senha, nome='Equipe Suporte')
        cls.chamado = Chamado.objects.create(assunto='Falha na impressora', descricao='A impressora não imprime documentos.', urgencia='HIGH', usuario=cls.usuario)

    def setUp(self):
        self.pasta_anexos = tempfile.mkdtemp()
        self.configuracao_anexos = override_settings(MEDIA_ROOT=self.pasta_anexos)
        self.configuracao_anexos.enable()
        self.addCleanup(self.configuracao_anexos.disable)
        self.addCleanup(shutil.rmtree, self.pasta_anexos)
        self.api = APIClient()

    def autenticar(self, usuario=None):
        usuario = usuario or self.usuario
        resultado = self.api.post('/api/auth/login', {'email': usuario.email, 'password': self.senha}, format='json')
        self.assertEqual(resultado.status_code, 200)
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + resultado.data['accessToken'])
        return resultado.data

    def png(self):
        saida = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(saida, 'PNG')
        return SimpleUploadedFile('erro.png', saida.getvalue(), content_type='image/png')

    def test_login_returns_jwt_public_user_and_audit(self):
        resultado = self.autenticar()
        self.assertEqual(resultado['user']['role'], 'USER')
        self.assertNotIn('password', resultado['user'])
        self.assertNotIn('passwordHash', resultado['user'])
        self.assertTrue(RegistroLogin.objects.get().sucesso)
        self.assertEqual(self.api.get('/api/auth/me').data['email'], self.usuario.email)

    def test_failed_login_generic_and_audited(self):
        for email in [self.usuario.email, 'missing@example.com']:
            resultado = self.api.post('/api/auth/login', {'email': email, 'password': 'incorreta'}, format='json')
            self.assertEqual(resultado.status_code, 401)
            self.assertEqual(resultado.data['message'], 'E-mail ou senha inválidos.')
        self.assertEqual(RegistroLogin.objects.filter(sucesso=False).count(), 2)
        self.assertNotIn('password', [f.name for f in RegistroLogin._meta.fields])

    def test_login_normalizes_email(self):
        resposta = self.api.post('/api/auth/login', {'email': ' ANA@EXAMPLE.COM ', 'password': self.senha}, format='json')
        self.assertEqual(resposta.status_code, 200)

    def test_inactive_login_and_existing_token_rejected(self):
        self.autenticar()
        self.usuario.is_active = False
        self.usuario.save()
        self.assertEqual(self.api.get('/api/auth/me').status_code, 401)
        self.api.credentials()
        resposta = self.api.post('/api/auth/login', {'email': self.usuario.email, 'password': self.senha}, format='json')
        self.assertEqual(resposta.status_code, 401)
        self.assertTrue(RegistroLogin.objects.filter(motivo_falha='USUARIO_DESATIVADO').exists())

    def test_expired_and_malformed_tokens(self):
        token = jwt.encode({'sub': str(self.usuario.id), 'iat': timezone.now() - timedelta(days=2),
            'exp': timezone.now() - timedelta(days=1)}, settings.SECRET_KEY, algorithm='HS256')
        for valor in ['Bearer broken', 'Basic x', 'Bearer ' + token]:
            self.api.credentials(HTTP_AUTHORIZATION=valor)
            self.assertEqual(self.api.get('/api/auth/me').status_code, 401)

    def test_permission_uses_current_database_role(self):
        self.autenticar(self.admin)
        self.admin.perfil = 'USER'
        self.admin.is_superuser = False
        self.admin.save()
        self.assertEqual(self.api.get('/api/users').status_code, 403)

    def test_anonymous_api_is_protected(self):
        for url in ['/api/auth/me', '/api/users', '/api/chamados', f'/api/chamados/{self.chamado.id}']:
            self.assertEqual(self.api.get(url).status_code, 401)

    def test_admin_creates_lists_and_reads_user(self):
        self.autenticar(self.admin)
        resposta = self.api.post('/api/users', {'name': 'Carlos Santos', 'email': 'Carlos@example.com', 'password': self.senha}, format='json')
        self.assertEqual(resposta.status_code, 201)
        usuario = Usuario.objects.get(email='carlos@example.com')
        self.assertTrue(usuario.check_password(self.senha))
        self.assertNotEqual(usuario.password, self.senha)
        self.assertEqual(self.api.get('/api/users').status_code, 200)
        self.assertEqual(self.api.get(f'/api/users/{usuario.id}').data['role'], 'USER')

    def test_common_user_cannot_manage_users(self):
        self.autenticar()
        for resultado in [self.api.get('/api/users'), self.api.get(f'/api/users/{self.admin.id}'),
            self.api.post('/api/users', {'name': 'Ataque'}, format='json')]:
            self.assertEqual(resultado.status_code, 403)

    def test_duplicate_email_and_weak_password_rejected(self):
        self.autenticar(self.admin)
        resultado = self.api.post('/api/users', {'name': 'Duplicado', 'email': 'ANA@EXAMPLE.COM', 'password': self.senha}, format='json')
        self.assertIn(resultado.status_code, [400, 409])
        resultado = self.api.post('/api/users', {'name': 'Nova Conta', 'email': 'novo@example.com', 'password': '12345678'}, format='json')
        self.assertEqual(resultado.status_code, 400)

    def test_create_ticket_owner_status_and_sequential_protocol(self):
        self.autenticar()
        resultado = self.api.post('/api/chamados', {'assunto': 'Erro no sistema', 'descricao': 'O sistema não está abrindo hoje.',
            'urgencia': 'CRITICAL', 'userId': str(self.outra_pessoa.id), 'status': 'RESOLVED'}, format='json')
        self.assertEqual(resultado.status_code, 201)
        chamado = Chamado.objects.get(id=resultado.data['id'])
        self.assertEqual(chamado.usuario, self.usuario)
        self.assertEqual(chamado.status, 'OPEN')
        self.assertGreater(chamado.numero, self.chamado.numero)
        self.assertEqual(chamado.protocolo, f'HD-{chamado.numero:06d}')

    def test_owner_scoped_list_and_detail(self):
        outro_chamado = Chamado.objects.create(assunto='Privado', descricao='Detalhe privado da outra pessoa', urgencia='LOW', usuario=self.outra_pessoa)
        self.autenticar()
        self.assertEqual(len(self.api.get('/api/chamados').data['results']), 1)
        self.assertEqual(self.api.get(f'/api/chamados/{outro_chamado.id}').status_code, 404)
        self.autenticar(self.admin)
        self.assertEqual(len(self.api.get('/api/chamados').data['results']), 2)
        self.assertEqual(self.api.get(f'/api/chamados/{outro_chamado.id}').status_code, 200)

    def test_status_admin_only_resolution_reopening_and_history(self):
        url = f'/api/chamados/{self.chamado.id}/status'
        self.autenticar()
        self.assertEqual(self.api.patch(url, {'status': 'RESOLVED'}, format='json').status_code, 403)
        self.autenticar(self.admin)
        self.assertEqual(self.api.patch(url, {'status': 'INVALID'}, format='json').status_code, 400)
        for status in ['IN_PROGRESS', 'RESOLVED', 'OPEN']:
            self.assertEqual(self.api.patch(url, {'status': status,
                'solucao': 'Impressora configurada e testada com sucesso.',
                'motivo': 'Problema voltou a ocorrer.'}, format='json').status_code, 200)
            self.chamado.refresh_from_db()
            self.assertEqual(self.chamado.resolvido_em is not None, status == 'RESOLVED')
        self.assertEqual(HistoricoStatus.objects.count(), 3)
        self.api.patch(url, {'status': 'OPEN'}, format='json')
        self.assertEqual(HistoricoStatus.objects.count(), 3)

    def test_conversation_between_owner_and_admin(self):
        url = f'/api/chamados/{self.chamado.id}/mensagens'
        self.autenticar()
        self.assertEqual(self.api.post(url, {'conteudo': '   '}, format='json').status_code, 400)
        self.assertEqual(self.api.post(url, {'conteudo': 'Preciso de ajuda', 'autorId': str(self.admin.id)}, format='json').status_code, 201)
        self.autenticar(self.admin)
        self.assertEqual(self.api.post(url, {'conteudo': 'Vamos verificar'}, format='json').status_code, 201)
        dados = self.api.get(f'/api/chamados/{self.chamado.id}').data
        self.assertEqual([m['autor']['role'] for m in dados['mensagens']], ['USER', 'ADMIN'])
        self.autenticar(self.outra_pessoa)
        self.assertEqual(self.api.post(url, {'conteudo': 'Intruso'}, format='json').status_code, 404)

    def test_private_attachment_upload_and_download(self):
        self.autenticar()
        resultado = self.api.post('/api/chamados', {'assunto': 'Erro com imagem', 'descricao': 'Segue a imagem do problema.', 'urgencia': 'MEDIUM', 'anexo': self.png()}, format='multipart')
        self.assertEqual(resultado.status_code, 201)
        c = resultado.data
        self.assertNotIn('storagePath', c['attachments'][0])
        url = f"/api/chamados/{c['id']}/anexos/{c['attachments'][0]['id']}"
        resposta = self.api.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('attachment;', resposta['Content-Disposition'])
        self.assertTrue(b''.join(resposta.streaming_content).startswith(b'\x89PNG'))
        self.autenticar(self.admin)
        resposta = self.api.get(url)
        self.assertEqual(resposta.status_code, 200)
        b''.join(resposta.streaming_content)
        self.autenticar(self.outra_pessoa)
        self.assertEqual(self.api.get(url).status_code, 404)
        self.assertEqual(self.client.get('/media/anexos/erro.png').status_code, 404)

    def test_attachment_must_belong_to_url_ticket(self):
        self.autenticar()
        criado = services.criar_chamado(self.usuario, {'assunto': 'Segundo chamado', 'descricao': 'Descrição de outro chamado', 'urgencia': 'LOW', 'anexo': self.png()})
        anexo = criado.anexos.get()
        self.assertEqual(self.api.get(f'/api/chamados/{self.chamado.id}/anexos/{anexo.id}').status_code, 404)

    def test_missing_attachment_returns_404(self):
        self.autenticar()
        a = Anexo.objects.create(chamado=self.chamado, nome='ausente.pdf', tipo='application/pdf', tamanho=20, arquivo='anexos/ausente.pdf')
        self.assertEqual(self.api.get(f'/api/chamados/{self.chamado.id}/anexos/{a.id}').status_code, 404)

    def test_upload_rejects_invalid_oversized_and_fake_files(self):
        self.autenticar()
        for arquivo in [SimpleUploadedFile('virus.exe', b'bad'), SimpleUploadedFile('fake.png', b'bad', content_type='image/png'),
            SimpleUploadedFile('fake.pdf', b'not pdf', content_type='application/pdf'),
            SimpleUploadedFile('large.pdf', b'%PDF-' + b'x' * (5 * 1024 * 1024), content_type='application/pdf')]:
            resultado = self.api.post('/api/chamados', {'assunto': 'Erro com anexo', 'descricao': 'Descrição suficiente para chamado', 'urgencia': 'HIGH', 'anexo': arquivo}, format='multipart')
            self.assertEqual(resultado.status_code, 400)
        self.assertEqual(Anexo.objects.count(), 0)

    def test_pdf_accepted(self):
        formulario = FormularioChamado({'assunto': 'Anexo PDF', 'descricao': 'Documento com detalhes da falha', 'urgencia': 'LOW'},
            {'anexo': SimpleUploadedFile('documento.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')})
        self.assertTrue(formulario.is_valid(), formulario.errors)

    def test_large_allowed_upload_uses_temporary_file(self):
        self.autenticar()
        resultado = self.api.post('/api/chamados', {'assunto': 'PDF grande', 'descricao': 'Arquivo válido dentro do limite',
            'urgencia': 'LOW', 'anexo': SimpleUploadedFile('grande.pdf', b'%PDF-1.4\n' + b'x' * (3 * 1024 * 1024),
                content_type='application/pdf')}, format='multipart')
        self.assertEqual(resultado.status_code, 201)

    def test_invalid_ticket_fields(self):
        self.autenticar()
        for dados in [{'assunto': '  ', 'descricao': '1234567890', 'urgencia': 'LOW'},
            {'assunto': 'Assunto', 'descricao': 'curta', 'urgencia': 'LOW'},
            {'assunto': 'Assunto', 'descricao': '1234567890', 'urgencia': 'INVALID'}]:
            self.assertEqual(self.api.post('/api/chamados', dados, format='json').status_code, 400)

    def test_database_failure_rolls_back_ticket_and_file(self):
        with patch('chamados.models.Anexo.save', side_effect=DatabaseError('falha simulada')):
            with self.assertRaises(DatabaseError):
                services.criar_chamado(self.usuario, {'assunto': 'Anexo falha', 'descricao': 'Falha simulada na gravação', 'urgencia': 'LOW', 'anexo': self.png()})
        from pathlib import Path
        self.assertEqual(Chamado.objects.count(), 1)
        self.assertFalse(any(p.is_file() for p in Path(self.pasta_anexos).rglob('*')))

    def test_health_success_and_failure(self):
        self.assertTrue(self.api.get('/api/status').data['bancoConectado'])
        with patch('chamados.api.Usuario.objects.exists', side_effect=DatabaseError):
            self.assertEqual(self.api.get('/api/status').status_code, 503)

    def test_html_pages_for_user_and_admin(self):
        self.client.force_login(self.usuario)
        for url in ['/home', '/tickets/new', f'/tickets/{self.chamado.id}']:
            self.assertEqual(self.client.get(url).status_code, 200)
        for url in ['/admin', '/admin/users', '/admin/logins', f'/admin/users/{self.outra_pessoa.id}']:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        for url in ['/admin', '/admin/users', '/admin/logins', f'/admin/users/{self.usuario.id}',
            f'/tickets/{self.chamado.id}', '/django-admin/chamados/usuario/add/']:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_html_csrf_login_create_message_status_and_logout(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.get('/login').status_code, 200)
        self.assertEqual(cliente.post('/login', {'email': self.usuario.email, 'password': self.senha}).status_code, 403)
        token = cliente.cookies['csrftoken'].value
        self.assertEqual(cliente.post('/login', {'email': self.usuario.email, 'password': self.senha, 'csrfmiddlewaretoken': token}).status_code, 302)
        token = cliente.cookies['csrftoken'].value
        resposta = cliente.post('/tickets/new', {'assunto': 'Novo na interface', 'descricao': 'Descrição do novo chamado HTML', 'urgencia': 'LOW', 'csrfmiddlewaretoken': token})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(cliente.post(resposta.url, {'conteudo': 'Mensagem da interface', 'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(cliente.get('/logout').status_code, 405)
        self.assertEqual(cliente.post('/logout', {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(cliente.get('/home').status_code, 302)

    def test_html_search_status_and_escaping(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get('/home', {'q': self.chamado.protocolo}), self.chamado.assunto)
        self.assertNotContains(self.client.get('/home', {'status': 'RESOLVED'}), self.chamado.assunto)
        self.chamado.descricao = '<script>alert(1)</script>'
        self.chamado.save()
        resposta = self.client.get(f'/tickets/{self.chamado.id}')
        self.assertContains(resposta, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(resposta, '<script>alert(1)</script>')

    def test_html_cross_user_details_and_messages_blocked(self):
        self.client.force_login(self.outra_pessoa)
        url = f'/tickets/{self.chamado.id}'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'conteudo': 'Ataque'}).status_code, 404)

    def test_unknown_ids_and_malformed_json(self):
        self.autenticar()
        self.assertEqual(self.api.get('/api/chamados/not-a-uuid').status_code, 404)
        self.assertEqual(self.api.post('/api/chamados', '[', content_type='application/json').status_code, 400)
        self.assertEqual(self.api.post('/api/chamados', [], format='json').status_code, 400)

    def test_delete_user_preserves_ticket_message_file_history_and_audit(self):
        chamado = services.criar_chamado(self.usuario, {'assunto': 'Preservar anexo',
            'descricao': 'Os dados devem continuar disponíveis.', 'urgencia': 'LOW', 'anexo': self.png()})
        mensagem = services.enviar_mensagem(self.usuario, chamado.id, 'Minha mensagem')
        historico = HistoricoStatus.objects.create(chamado=chamado, autor=self.usuario,
            anterior='OPEN', novo='IN_PROGRESS')
        registro = RegistroLogin.objects.create(usuario=self.usuario,
            email_informado=self.usuario.email, sucesso=True)
        anexo = chamado.anexos.get()
        self.autenticar(self.admin)
        resposta = self.api.delete(f'/api/users/{self.usuario.id}')
        self.assertEqual(resposta.status_code, 204)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)
        self.assertFalse(self.usuario.has_usable_password())
        self.assertIsNotNone(self.usuario.excluido_em)
        self.assertEqual(self.usuario.excluido_por, self.admin)
        for obj in [chamado, mensagem, historico, registro, anexo]:
            obj.refresh_from_db()
        self.assertEqual(chamado.usuario, self.usuario)
        self.assertEqual(mensagem.autor, self.usuario)
        self.assertEqual(historico.autor, self.usuario)
        self.assertEqual(registro.usuario, self.usuario)
        self.assertTrue(anexo.arquivo.storage.exists(anexo.arquivo.name))
        self.assertEqual(self.api.get(f'/api/chamados/{chamado.id}').status_code, 200)
        resposta = self.api.get(f'/api/chamados/{chamado.id}/anexos/{anexo.id}')
        self.assertEqual(resposta.status_code, 200)
        b''.join(resposta.streaming_content)

    def test_deleted_user_disappears_from_html_and_api_but_keeps_email_reserved(self):
        services.excluir_usuario(self.admin, self.usuario.id)
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get('/admin/users'), self.usuario.email)
        self.assertEqual(self.client.get(f'/admin/users/{self.usuario.id}').status_code, 404)
        self.autenticar(self.admin)
        self.assertNotIn(str(self.usuario.id), [u['id'] for u in self.api.get('/api/users').data['results']])
        self.assertEqual(self.api.get(f'/api/users/{self.usuario.id}').status_code, 404)
        self.assertEqual(self.api.post('/api/users', {'name': 'Outra Ana',
            'email': self.usuario.email, 'password': self.senha}, format='json').status_code, 400)

    def test_deleted_user_loses_existing_session_token_and_login(self):
        self.autenticar()
        self.client.force_login(self.usuario)
        services.excluir_usuario(self.admin, self.usuario.id)
        self.assertEqual(self.api.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.client.get('/home').status_code, 302)
        self.api.credentials()
        self.assertEqual(self.api.post('/api/auth/login', {'email': self.usuario.email,
            'password': self.senha}, format='json').status_code, 401)
        resposta = self.client.post('/login', {'email': self.usuario.email, 'password': self.senha})
        self.assertContains(resposta, 'E-mail ou senha inválidos.')

    def test_delete_requires_admin_in_html_api_and_service(self):
        url = f'/admin/users/{self.outra_pessoa.id}/excluir'
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.api.delete(f'/api/users/{self.outra_pessoa.id}').status_code, 401)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'confirmar': 'sim'}).status_code, 403)
        self.autenticar()
        self.assertEqual(self.api.delete(f'/api/users/{self.outra_pessoa.id}').status_code, 403)
        with self.assertRaises(PermissionDenied):
            services.excluir_usuario(self.usuario, self.outra_pessoa.id)
        self.outra_pessoa.refresh_from_db()
        self.assertIsNone(self.outra_pessoa.excluido_em)

    def test_admin_cannot_delete_self(self):
        self.autenticar(self.admin)
        self.assertEqual(self.api.delete(f'/api/users/{self.admin.id}').status_code, 400)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f'/admin/users/{self.admin.id}/excluir',
            {'confirmar': 'sim'}).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertIsNone(self.admin.excluido_em)

    def test_portal_admin_can_delete_other_users_but_not_technical_accounts(self):
        operador = Usuario.objects.create_user('operador@example.com', self.senha,
            nome='Operador', perfil='ADMIN')
        colega = Usuario.objects.create_user('colega@example.com', self.senha,
            nome='Colega', perfil='ADMIN')
        tecnico = Usuario.objects.create_user('tecnico@example.com', self.senha,
            nome='Técnico', is_staff=True)
        self.autenticar(operador)
        for alvo in [self.admin, tecnico]:
            self.assertEqual(self.api.delete(f'/api/users/{alvo.id}').status_code, 403)
        for alvo in [self.outra_pessoa, colega]:
            self.assertEqual(self.api.delete(f'/api/users/{alvo.id}').status_code, 204)

    def test_delete_confirmation_get_cancel_csrf_and_explicit_post(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        url = f'/admin/users/{self.outra_pessoa.id}/excluir'
        resposta = cliente.get(url)
        self.assertContains(resposta, self.outra_pessoa.email)
        self.assertContains(resposta, 'Cancelar')
        self.outra_pessoa.refresh_from_db()
        self.assertIsNone(self.outra_pessoa.excluido_em)
        self.assertEqual(cliente.post(url, {'confirmar': 'sim'}).status_code, 403)
        token = cliente.cookies['csrftoken'].value
        self.assertEqual(cliente.post(url, {'csrfmiddlewaretoken': token}).status_code, 200)
        self.outra_pessoa.refresh_from_db()
        self.assertIsNone(self.outra_pessoa.excluido_em)
        resposta = cliente.post(url, {'csrfmiddlewaretoken': token, 'confirmar': 'sim'})
        self.assertRedirects(resposta, '/admin/users')
        self.outra_pessoa.refresh_from_db()
        self.assertIsNotNone(self.outra_pessoa.excluido_em)

    def test_delete_buttons_and_new_password_autocomplete(self):
        self.client.force_login(self.admin)
        resposta = self.client.get('/admin/users')
        self.assertContains(resposta, f'/admin/users/{self.outra_pessoa.id}/excluir')
        self.assertNotContains(resposta, f'/admin/users/{self.admin.id}/excluir')
        self.assertContains(resposta, 'autocomplete="new-password"')
        self.assertContains(self.client.get(f'/admin/users/{self.outra_pessoa.id}'), 'Excluir usuário')

    def test_repeat_or_missing_delete_returns_404_without_overwriting_audit(self):
        import uuid
        self.autenticar(self.admin)
        self.assertEqual(self.api.delete(f'/api/users/{uuid.uuid4()}').status_code, 404)
        self.assertEqual(self.api.delete(f'/api/users/{self.outra_pessoa.id}').status_code, 204)
        self.outra_pessoa.refresh_from_db()
        excluido_em = self.outra_pessoa.excluido_em
        self.assertEqual(self.api.delete(f'/api/users/{self.outra_pessoa.id}').status_code, 404)
        self.outra_pessoa.refresh_from_db()
        self.assertEqual(self.outra_pessoa.excluido_em, excluido_em)

    def test_stale_deleted_admin_cannot_delete_another_account(self):
        operador = Usuario.objects.create_user('stale@example.com', self.senha,
            nome='Operador', perfil='ADMIN')
        services.excluir_usuario(self.admin, operador.id)
        with self.assertRaises(PermissionDenied):
            services.excluir_usuario(operador, self.outra_pessoa.id)
        self.outra_pessoa.refresh_from_db()
        self.assertIsNone(self.outra_pessoa.excluido_em)

    def test_database_prevents_reactivating_deleted_user(self):
        services.excluir_usuario(self.admin, self.outra_pessoa.id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.filter(pk=self.outra_pessoa.id).update(is_active=True)

    def test_technical_admin_and_command_cannot_bypass_soft_deletion(self):
        self.client.force_login(self.admin)
        caminho = f'/django-admin/chamados/usuario/{self.outra_pessoa.pk}'
        self.assertEqual(self.client.get(caminho + '/delete/').status_code, 403)
        services.excluir_usuario(self.admin, self.outra_pessoa.id)
        self.assertEqual(self.client.post(caminho + '/change/', {'is_active': True}).status_code, 403)
        self.assertEqual(self.client.post(caminho + '/password/', {
            'password1': self.senha, 'password2': self.senha}).status_code, 403)
        with patch.dict('os.environ', {'INITIAL_ADMIN_PASSWORD': self.senha}):
            with self.assertRaisesMessage(CommandError, 'Esta conta foi excluída'):
                call_command('criar_admin', email=self.outra_pessoa.email, nome='Outra',
                    atualizar_senha=True, stdout=io.StringIO())
