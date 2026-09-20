import io
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Usuario, Chamado, Categoria, MensagemChamado, Anexo, Notificacao, EventoChamado
from .forms import ChamadoForm, GerenciarForm
from . import fluxo, services


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AtendimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.senha = 'SenhaAtendimento!904'
        cls.admin = Usuario.objects.create_superuser('suporte@test.local', cls.senha, name='Suporte')
        cls.tecnico = Usuario.objects.create_user('tecnico@test.local', cls.senha, name='Técnico', role='ADMIN')
        cls.user = Usuario.objects.create_user('pessoa@test.local', cls.senha, name='Solicitante')
        cls.other = Usuario.objects.create_user('outra@test.local', cls.senha, name='Outra pessoa')
        cls.categoria = Categoria.objects.get(nome='Internet')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.api = APIClient()
        self.c = services.criar_chamado(self.user, {'assunto': 'Internet indisponível',
            'descricao': 'A rede não funciona no laboratório.', 'urgencia': 'HIGH', 'categoria': self.categoria})

    def pdf(self, name='documento.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4\n%%EOF', content_type='application/pdf')

    def auth(self, usuario):
        self.api.force_authenticate(usuario)

    def resolver(self, c=None):
        return fluxo.mudar_status(self.admin, (c or self.c).id, 'RESOLVED',
            solucao='Conexão restabelecida após substituir o equipamento.')

    def test_creation_category_deadlines_notifications(self):
        self.assertEqual(self.c.categoria, self.categoria)
        self.assertAlmostEqual((self.c.prazo_resposta - self.c.criado_em).total_seconds(), 7200, delta=2)
        self.assertAlmostEqual((self.c.prazo_resolucao - self.c.criado_em).total_seconds(), 28800, delta=2)
        self.assertTrue(Notificacao.objects.filter(chamado=self.c, usuario=self.admin).exists())
        self.assertFalse(Notificacao.objects.filter(chamado=self.c, usuario=self.other).exists())

    def test_assignment_transfer_and_audit(self):
        fluxo.gerenciar(self.admin, self.c.id, {'responsavel': self.tecnico})
        fluxo.gerenciar(self.admin, self.c.id, {'responsavel': self.admin})
        self.c.refresh_from_db()
        self.assertEqual(self.c.responsavel, self.admin)
        self.assertEqual(self.c.eventos.filter(campo='Responsável').count(), 2)
        self.assertTrue(Notificacao.objects.filter(usuario=self.tecnico, titulo__contains='Responsável').exists())

    def test_non_admin_and_inactive_assignment_rejected(self):
        with self.assertRaises(PermissionDenied):
            fluxo.gerenciar(self.user, self.c.id, {'responsavel': self.tecnico})
        self.tecnico.is_active = False
        self.tecnico.save()
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.c.id, {'responsavel': self.tecnico})
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.c.id, {'responsavel': self.user})

    def test_category_and_urgency_audited_without_resetting_sla(self):
        original = self.c.prazo_resolucao
        outra = Categoria.objects.get(nome='Computador')
        fluxo.gerenciar(self.admin, self.c.id, {'categoria': outra, 'urgencia': 'CRITICAL'})
        self.c.refresh_from_db()
        self.assertEqual(self.c.categoria, outra)
        self.assertEqual(self.c.urgencia, 'CRITICAL')
        self.assertEqual(self.c.prazo_resolucao, original)
        self.assertTrue(self.c.eventos.filter(campo='Categoria').exists())
        self.assertTrue(self.c.eventos.filter(campo='Urgência').exists())

    def test_pause_and_resume_extend_sla(self):
        now = timezone.now()
        original = self.c.prazo_resolucao
        response = self.c.prazo_resposta
        with patch('chamados.fluxo.timezone.now', return_value=now):
            fluxo.mudar_status(self.admin, self.c.id, 'WAITING_USER')
        with patch('chamados.fluxo.timezone.now', return_value=now + timedelta(hours=3)):
            services.enviar_mensagem(self.user, self.c.id, 'Enviei os detalhes solicitados.')
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, 'IN_PROGRESS')
        self.assertIsNone(self.c.pausa_iniciada_em)
        self.assertEqual(self.c.segundos_pausados, 10800)
        self.assertEqual(self.c.prazo_resolucao, original + timedelta(hours=3))
        self.assertEqual(self.c.prazo_resposta, response + timedelta(hours=3))

    def test_third_party_does_not_pause_and_internal_note_is_not_response(self):
        fluxo.mudar_status(self.admin, self.c.id, 'WAITING_THIRD')
        services.enviar_mensagem(self.admin, self.c.id, 'Diagnóstico privado', interna=True)
        self.c.refresh_from_db()
        self.assertIsNone(self.c.pausa_iniciada_em)
        self.assertIsNone(self.c.primeira_resposta_em)
        services.enviar_mensagem(self.admin, self.c.id, 'Estamos verificando sua conexão.')
        self.c.refresh_from_db()
        self.assertIsNotNone(self.c.primeira_resposta_em)

    def test_deadline_change_requires_reason_and_history(self):
        novo = self.c.prazo_resolucao + timedelta(hours=1)
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.c.id, {'prazo_resolucao': novo})
        fluxo.gerenciar(self.admin, self.c.id, {'prazo_resolucao': novo, 'motivo': 'Aguardando visita técnica'})
        self.c.refresh_from_db()
        self.assertEqual(self.c.prazo_resolucao, novo)
        self.assertTrue(self.c.eventos.filter(campo='Prazo de resolução', motivo='Aguardando visita técnica').exists())
        fluxo.mudar_status(self.admin, self.c.id, 'WAITING_USER')
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.c.id, {'prazo_resolucao': novo + timedelta(hours=1), 'motivo': 'Teste'})

    def test_overdue_and_near_deadline_indicators(self):
        self.c.prazo_resposta = timezone.now() - timedelta(minutes=1)
        self.assertEqual(self.c.situacao_prazo, 'Atrasado')
        self.c.prazo_resposta = timezone.now() + timedelta(minutes=30)
        self.assertEqual(self.c.situacao_prazo, 'Vence em até 1 hora')
        self.c.pausa_iniciada_em = timezone.now()
        self.assertEqual(self.c.situacao_prazo, 'Pausado')

    def test_solution_required_owner_confirmation_and_reopen(self):
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.c.id, 'RESOLVED')
        self.resolver()
        self.auth(self.other)
        self.assertEqual(self.api.post(f'/api/chamados/{self.c.id}/confirmar').status_code, 404)
        self.auth(self.admin)
        self.assertEqual(self.api.post(f'/api/chamados/{self.c.id}/confirmar').status_code, 404)
        fluxo.confirmar(self.user, self.c.id)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, 'CLOSED')
        self.assertIsNotNone(self.c.confirmado_em)
        with self.assertRaises(ValidationError):
            fluxo.reabrir(self.user, self.c.id, '')
        fluxo.reabrir(self.user, self.c.id, 'A conexão parou novamente.')
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, 'OPEN')
        self.assertEqual(self.c.solucao, '')
        self.assertIsNone(self.c.confirmado_em)
        self.assertTrue(self.c.mensagens.filter(conteudo__startswith='Reabertura:').exists())

    def test_cancel_requires_reason_and_closed_message_rejected(self):
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.c.id, 'CANCELLED')
        fluxo.mudar_status(self.admin, self.c.id, 'CANCELLED', motivo='Solicitação aberta por engano.')
        with self.assertRaises(ValidationError):
            services.enviar_mensagem(self.user, self.c.id, 'Uma mensagem')
        fluxo.mudar_status(self.admin, self.c.id, 'OPEN', motivo='Retomar atendimento.')
        self.resolver()
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.c.id, 'CLOSED')

    def test_internal_notes_and_attachments_are_private_in_all_routes(self):
        msg = services.enviar_mensagem(self.admin, self.c.id, 'SEGREDO INTERNO',
            interna=True, anexo=[self.pdf('interno.pdf')])
        anexo = msg.anexos.get()
        self.auth(self.user)
        detail = self.api.get(f'/api/chamados/{self.c.id}').data
        self.assertNotIn('SEGREDO INTERNO', str(detail))
        self.assertNotIn('interno.pdf', str(detail))
        self.assertNotIn('SEGREDO INTERNO', str(self.api.get(f'/api/chamados/{self.c.id}/mensagens').data))
        self.assertEqual(self.api.get(f'/api/chamados/{self.c.id}/anexos/{anexo.id}').status_code, 404)
        self.assertFalse(fluxo.eventos_visiveis(self.c, self.user).filter(interno=True).exists())
        self.client.force_login(self.user)
        response = self.client.get(f'/tickets/{self.c.id}')
        self.assertNotContains(response, 'SEGREDO INTERNO')
        self.assertNotContains(response, 'interno.pdf')
        self.auth(self.tecnico)
        response = self.api.get(f'/api/chamados/{self.c.id}/anexos/{anexo.id}')
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)

    def test_user_cannot_post_internal_note(self):
        self.auth(self.user)
        result = self.api.post(f'/api/chamados/{self.c.id}/mensagens',
            {'conteudo': 'Teste privado', 'interna': True}, format='json')
        self.assertEqual(result.status_code, 403)
        self.assertFalse(self.c.mensagens.exists())

    def test_multiple_uploads_at_creation_and_conversation(self):
        self.auth(self.user)
        response = self.api.post('/api/chamados', {'assunto': 'Mais anexos',
            'descricao': 'Descrição com múltiplos arquivos.', 'urgencia': 'LOW',
            'anexo': [self.pdf('um.pdf'), self.pdf('dois.pdf')]}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data['attachments']), 2)
        result = self.api.post(f'/api/chamados/{self.c.id}/mensagens',
            {'conteudo': 'Arquivos complementares.', 'anexo': [self.pdf('tres.pdf'), self.pdf('quatro.pdf')]},
            format='multipart')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(len(result.data['attachments']), 2)

    def test_each_file_validated_and_count_limited(self):
        self.auth(self.user)
        for arquivos in [[self.pdf(), SimpleUploadedFile('falso.png', b'bad')],
                         [self.pdf(f'{i}.pdf') for i in range(6)]]:
            result = self.api.post(f'/api/chamados/{self.c.id}/mensagens',
                {'conteudo': 'Arquivos inválidos.', 'anexo': arquivos}, format='multipart')
            self.assertEqual(result.status_code, 400)
        self.assertFalse(self.c.mensagens.exists())
        self.assertFalse(Anexo.objects.exists())

    def test_upload_failure_rolls_back_message_files_and_notifications(self):
        before = Notificacao.objects.count()
        with patch('chamados.models.Anexo.save', side_effect=DatabaseError('simulada')):
            with self.assertRaises(DatabaseError):
                services.enviar_mensagem(self.user, self.c.id, 'Anexo com falha', anexo=[self.pdf()])
        self.assertFalse(self.c.mensagens.exists())
        self.assertEqual(Notificacao.objects.count(), before)
        self.assertFalse(any(p.is_file() for p in Path(self.temp.name).rglob('*')))

    def test_notifications_unread_and_isolated_per_user(self):
        services.enviar_mensagem(self.admin, self.c.id, 'Resposta da equipe.')
        self.auth(self.user)
        data = self.api.get('/api/notificacoes').data
        self.assertGreater(data['count'], 0)
        id = data['results'][0]['id']
        self.auth(self.other)
        self.assertEqual(self.api.post(f'/api/notificacoes/{id}/ler').status_code, 404)
        self.auth(self.user)
        self.assertEqual(self.api.post(f'/api/notificacoes/{id}/ler').status_code, 204)
        self.assertIsNotNone(Notificacao.objects.get(pk=id).lida_em)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/notificacoes').status_code, 200)

    def test_internal_notifications_hidden_after_demotion(self):
        services.enviar_mensagem(self.admin, self.c.id, 'Nota para equipe', interna=True)
        self.assertTrue(fluxo.notificacoes_visiveis(self.tecnico).filter(interna=True).exists())
        self.tecnico.role = 'USER'
        self.tecnico.save()
        self.assertFalse(fluxo.notificacoes_visiveis(self.tecnico).exists())

    def test_duplicate_resolution_notifies_each_owner_without_leaking_incident(self):
        filho = services.criar_chamado(self.other, {'assunto': 'Mesmo problema',
            'descricao': 'A rede da outra sala também caiu.', 'urgencia': 'HIGH'})
        fluxo.vincular(self.admin, filho.id, self.c)
        services.enviar_mensagem(self.admin, self.c.id, 'INFORMAÇÃO RESTRITA', interna=True)
        self.resolver()
        filho.refresh_from_db()
        self.assertEqual(filho.status, 'RESOLVED')
        self.assertTrue(filho.solucao)
        self.assertTrue(Notificacao.objects.filter(chamado=filho, usuario=self.other, interna=False).exists())
        self.auth(self.other)
        self.assertEqual(self.api.get(f'/api/chamados/{self.c.id}').status_code, 404)
        detail = self.api.get(f'/api/chamados/{filho.id}').data
        self.assertNotIn('incidenteId', detail)
        self.assertNotIn('INFORMAÇÃO RESTRITA', str(detail))
        self.assertNotIn(self.c.assunto, str(detail))

    def test_duplicate_cycles_and_chains_rejected(self):
        filho = services.criar_chamado(self.other, {'assunto': 'Filho', 'descricao': 'Descrição do filho.', 'urgencia': 'LOW'})
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, self.c.id, self.c)
        fluxo.vincular(self.admin, filho.id, self.c)
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, self.c.id, filho)
        terceiro = services.criar_chamado(self.user, {'assunto': 'Terceiro', 'descricao': 'Descrição do terceiro.', 'urgencia': 'LOW'})
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, terceiro.id, filho)
        fluxo.vincular(self.admin, filho.id, None)
        filho.refresh_from_db()
        self.assertIsNone(filho.incidente_id)

    def test_management_and_workflow_api(self):
        self.auth(self.admin)
        r = self.api.patch(f'/api/chamados/{self.c.id}/gestao',
            {'responsavel': str(self.tecnico.pk)}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['responsavel']['id'], str(self.tecnico.pk))
        r = self.api.patch(f'/api/chamados/{self.c.id}/status',
            {'status': 'RESOLVED', 'solucao': 'Funcionamento restaurado e verificado.'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.auth(self.user)
        self.assertEqual(self.api.post(f'/api/chamados/{self.c.id}/confirmar').status_code, 200)
        r = self.api.post(f'/api/chamados/{self.c.id}/reabrir', {'motivo': 'Falha voltou a acontecer.'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.api.get(f'/api/chamados/{self.c.id}/historico').status_code, 200)

    def test_api_pagination_limits_tickets_and_messages(self):
        Chamado.objects.bulk_create([Chamado(usuario=self.user, assunto=f'Extra {i}',
            descricao='Descrição válida.', urgencia='LOW') for i in range(25)])
        MensagemChamado.objects.bulk_create([MensagemChamado(chamado=self.c, autor=self.user,
            conteudo=f'Mensagem {i}') for i in range(35)])
        self.auth(self.user)
        r = self.api.get('/api/chamados').data
        self.assertEqual(r['count'], 26)
        self.assertEqual(len(r['results']), 20)
        self.assertEqual(len(self.api.get('/api/chamados?page=2').data['results']), 6)
        detail = self.api.get(f'/api/chamados/{self.c.id}').data
        self.assertEqual(len(detail['mensagens']), 30)
        self.assertEqual(detail['mensagensTotal'], 35)
        self.assertEqual(len(self.api.get(f'/api/chamados/{self.c.id}/mensagens?page=2').data['results']), 5)

    def test_dashboard_filters_and_get_has_no_workflow_side_effect(self):
        fluxo.gerenciar(self.admin, self.c.id, {'responsavel': self.admin})
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin', {'meus': '1', 'categoria': self.categoria.pk}), self.c.assunto)
        self.assertNotContains(self.client.get('/admin', {'fila': 'sem'}), self.c.assunto)
        self.assertEqual(self.client.get(f'/tickets/{self.c.id}/acoes/confirmar').status_code, 405)
        self.assertEqual(self.client.get(f'/tickets/{self.c.id}').status_code, 200)

    def test_portal_management_preserves_second_precision_for_unchanged_dates(self):
        self.client.force_login(self.admin)
        dados = {'responsavel': str(self.tecnico.pk), 'categoria': self.categoria.pk, 'urgencia': 'HIGH',
            'prazo_resposta': timezone.localtime(self.c.prazo_resposta).strftime('%Y-%m-%dT%H:%M'),
            'prazo_resolucao': timezone.localtime(self.c.prazo_resolucao).strftime('%Y-%m-%dT%H:%M')}
        r = self.client.post(f'/tickets/{self.c.id}/acoes/gerenciar', dados)
        self.assertEqual(r.status_code, 302)
        self.c.refresh_from_db()
        self.assertEqual(self.c.responsavel, self.tecnico)
