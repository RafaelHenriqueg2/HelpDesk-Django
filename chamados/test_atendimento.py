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
from .forms import FormularioChamado, FormularioGestao
from . import fluxo, services


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TestesAtendimento(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.senha = 'SenhaAtendimento!904'
        cls.admin = Usuario.objects.create_superuser('suporte@test.local', cls.senha, nome='Suporte')
        cls.tecnico = Usuario.objects.create_user('tecnico@test.local', cls.senha, nome='Técnico', perfil='ADMIN')
        cls.usuario = Usuario.objects.create_user('pessoa@test.local', cls.senha, nome='Solicitante')
        cls.outra_pessoa = Usuario.objects.create_user('outra@test.local', cls.senha, nome='Outra pessoa')
        cls.categoria = Categoria.objects.get(nome='Internet')

    def setUp(self):
        self.pasta_temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta_temporaria.cleanup)
        self.configuracao_anexos = override_settings(MEDIA_ROOT=self.pasta_temporaria.name)
        self.configuracao_anexos.enable()
        self.addCleanup(self.configuracao_anexos.disable)
        self.api = APIClient()
        self.chamado = services.criar_chamado(self.usuario, {'assunto': 'Internet indisponível',
            'descricao': 'A rede não funciona no laboratório.', 'urgencia': 'HIGH', 'categoria': self.categoria})

    def pdf(self, name='documento.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4\n%%EOF', content_type='application/pdf')

    def autenticar(self, usuario):
        self.api.force_authenticate(usuario)

    def resolver(self, c=None):
        return fluxo.mudar_status(self.admin, (c or self.chamado).id, 'RESOLVED',
            solucao='Conexão restabelecida após substituir o equipamento.')

    def test_creation_category_deadlines_notifications(self):
        self.assertEqual(self.chamado.categoria, self.categoria)
        self.assertAlmostEqual((self.chamado.prazo_resposta - self.chamado.criado_em).total_seconds(), 7200, delta=2)
        self.assertAlmostEqual((self.chamado.prazo_resolucao - self.chamado.criado_em).total_seconds(), 28800, delta=2)
        self.assertTrue(Notificacao.objects.filter(chamado=self.chamado, usuario=self.admin).exists())
        self.assertFalse(Notificacao.objects.filter(chamado=self.chamado, usuario=self.outra_pessoa).exists())

    def test_assignment_transfer_and_audit(self):
        fluxo.gerenciar(self.admin, self.chamado.id, {'responsavel': self.tecnico})
        fluxo.gerenciar(self.admin, self.chamado.id, {'responsavel': self.admin})
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.responsavel, self.admin)
        self.assertEqual(self.chamado.eventos.filter(campo='Responsável').count(), 2)
        self.assertTrue(Notificacao.objects.filter(usuario=self.tecnico, titulo__contains='Responsável').exists())

    def test_non_admin_and_inactive_assignment_rejected(self):
        with self.assertRaises(PermissionDenied):
            fluxo.gerenciar(self.usuario, self.chamado.id, {'responsavel': self.tecnico})
        self.tecnico.is_active = False
        self.tecnico.save()
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.chamado.id, {'responsavel': self.tecnico})
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.chamado.id, {'responsavel': self.usuario})

    def test_category_and_urgency_audited_without_resetting_sla(self):
        original = self.chamado.prazo_resolucao
        outra = Categoria.objects.get(nome='Computador')
        fluxo.gerenciar(self.admin, self.chamado.id, {'categoria': outra, 'urgencia': 'CRITICAL'})
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.categoria, outra)
        self.assertEqual(self.chamado.urgencia, 'CRITICAL')
        self.assertEqual(self.chamado.prazo_resolucao, original)
        self.assertTrue(self.chamado.eventos.filter(campo='Categoria').exists())
        self.assertTrue(self.chamado.eventos.filter(campo='Urgência').exists())

    def test_pause_and_resume_extend_sla(self):
        agora = timezone.now()
        original = self.chamado.prazo_resolucao
        resposta = self.chamado.prazo_resposta
        with patch('chamados.fluxo.timezone.now', return_value=agora):
            fluxo.mudar_status(self.admin, self.chamado.id, 'WAITING_USER')
        with patch('chamados.fluxo.timezone.now', return_value=agora + timedelta(hours=3)):
            services.enviar_mensagem(self.usuario, self.chamado.id, 'Enviei os detalhes solicitados.')
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'IN_PROGRESS')
        self.assertIsNone(self.chamado.pausa_iniciada_em)
        self.assertEqual(self.chamado.segundos_pausados, 10800)
        self.assertEqual(self.chamado.prazo_resolucao, original + timedelta(hours=3))
        self.assertEqual(self.chamado.prazo_resposta, resposta + timedelta(hours=3))

    def test_third_party_does_not_pause_and_internal_note_is_not_response(self):
        fluxo.mudar_status(self.admin, self.chamado.id, 'WAITING_THIRD')
        services.enviar_mensagem(self.admin, self.chamado.id, 'Diagnóstico privado', interna=True)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.pausa_iniciada_em)
        self.assertIsNone(self.chamado.primeira_resposta_em)
        services.enviar_mensagem(self.admin, self.chamado.id, 'Estamos verificando sua conexão.')
        self.chamado.refresh_from_db()
        self.assertIsNotNone(self.chamado.primeira_resposta_em)

    def test_deadline_change_requires_reason_and_history(self):
        novo = self.chamado.prazo_resolucao + timedelta(hours=1)
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.chamado.id, {'prazo_resolucao': novo})
        fluxo.gerenciar(self.admin, self.chamado.id, {'prazo_resolucao': novo, 'motivo': 'Aguardando visita técnica'})
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.prazo_resolucao, novo)
        self.assertTrue(self.chamado.eventos.filter(campo='Prazo de resolução', motivo='Aguardando visita técnica').exists())
        fluxo.mudar_status(self.admin, self.chamado.id, 'WAITING_USER')
        with self.assertRaises(ValidationError):
            fluxo.gerenciar(self.admin, self.chamado.id, {'prazo_resolucao': novo + timedelta(hours=1), 'motivo': 'Teste'})

    def test_overdue_and_near_deadline_indicators(self):
        self.chamado.prazo_resposta = timezone.now() - timedelta(minutes=1)
        self.assertEqual(self.chamado.situacao_prazo, 'Atrasado')
        self.chamado.prazo_resposta = timezone.now() + timedelta(minutes=30)
        self.assertEqual(self.chamado.situacao_prazo, 'Vence em até 1 hora')
        self.chamado.pausa_iniciada_em = timezone.now()
        self.assertEqual(self.chamado.situacao_prazo, 'Pausado')

    def test_solution_required_owner_confirmation_and_reopen(self):
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.chamado.id, 'RESOLVED')
        self.resolver()
        self.autenticar(self.outra_pessoa)
        self.assertEqual(self.api.post(f'/api/chamados/{self.chamado.id}/confirmar').status_code, 404)
        self.autenticar(self.admin)
        self.assertEqual(self.api.post(f'/api/chamados/{self.chamado.id}/confirmar').status_code, 404)
        fluxo.confirmar(self.usuario, self.chamado.id)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'CLOSED')
        self.assertIsNotNone(self.chamado.confirmado_em)
        with self.assertRaises(ValidationError):
            fluxo.reabrir(self.usuario, self.chamado.id, '')
        fluxo.reabrir(self.usuario, self.chamado.id, 'A conexão parou novamente.')
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'OPEN')
        self.assertEqual(self.chamado.solucao, '')
        self.assertIsNone(self.chamado.confirmado_em)
        self.assertTrue(self.chamado.mensagens.filter(conteudo__startswith='Reabertura:').exists())

    def test_cancel_requires_reason_and_closed_message_rejected(self):
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.chamado.id, 'CANCELLED')
        fluxo.mudar_status(self.admin, self.chamado.id, 'CANCELLED', motivo='Solicitação aberta por engano.')
        with self.assertRaises(ValidationError):
            services.enviar_mensagem(self.usuario, self.chamado.id, 'Uma mensagem')
        fluxo.mudar_status(self.admin, self.chamado.id, 'OPEN', motivo='Retomar atendimento.')
        self.resolver()
        with self.assertRaises(ValidationError):
            fluxo.mudar_status(self.admin, self.chamado.id, 'CLOSED')

    def test_internal_notes_and_attachments_are_private_in_all_routes(self):
        mensagem_criada = services.enviar_mensagem(self.admin, self.chamado.id, 'SEGREDO INTERNO',
            interna=True, anexo=[self.pdf('interno.pdf')])
        anexo = mensagem_criada.anexos.get()
        self.autenticar(self.usuario)
        detalhes = self.api.get(f'/api/chamados/{self.chamado.id}').data
        self.assertNotIn('SEGREDO INTERNO', str(detalhes))
        self.assertNotIn('interno.pdf', str(detalhes))
        self.assertNotIn('SEGREDO INTERNO', str(self.api.get(f'/api/chamados/{self.chamado.id}/mensagens').data))
        self.assertEqual(self.api.get(f'/api/chamados/{self.chamado.id}/anexos/{anexo.id}').status_code, 404)
        self.assertFalse(fluxo.eventos_visiveis(self.chamado, self.usuario).filter(interno=True).exists())
        self.client.force_login(self.usuario)
        resposta = self.client.get(f'/tickets/{self.chamado.id}')
        self.assertNotContains(resposta, 'SEGREDO INTERNO')
        self.assertNotContains(resposta, 'interno.pdf')
        self.autenticar(self.tecnico)
        resposta = self.api.get(f'/api/chamados/{self.chamado.id}/anexos/{anexo.id}')
        self.assertEqual(resposta.status_code, 200)
        b''.join(resposta.streaming_content)

    def test_user_cannot_post_internal_note(self):
        self.autenticar(self.usuario)
        resultado = self.api.post(f'/api/chamados/{self.chamado.id}/mensagens',
            {'conteudo': 'Teste privado', 'interna': True}, format='json')
        self.assertEqual(resultado.status_code, 403)
        self.assertFalse(self.chamado.mensagens.exists())

    def test_multiple_uploads_at_creation_and_conversation(self):
        self.autenticar(self.usuario)
        resposta = self.api.post('/api/chamados', {'assunto': 'Mais anexos',
            'descricao': 'Descrição com múltiplos arquivos.', 'urgencia': 'LOW',
            'anexo': [self.pdf('um.pdf'), self.pdf('dois.pdf')]}, format='multipart')
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(len(resposta.data['attachments']), 2)
        resultado = self.api.post(f'/api/chamados/{self.chamado.id}/mensagens',
            {'conteudo': 'Arquivos complementares.', 'anexo': [self.pdf('tres.pdf'), self.pdf('quatro.pdf')]},
            format='multipart')
        self.assertEqual(resultado.status_code, 201, resultado.data)
        self.assertEqual(len(resultado.data['attachments']), 2)

    def test_each_file_validated_and_count_limited(self):
        self.autenticar(self.usuario)
        for arquivos in [[self.pdf(), SimpleUploadedFile('falso.png', b'bad')],
                         [self.pdf(f'{i}.pdf') for i in range(6)]]:
            resultado = self.api.post(f'/api/chamados/{self.chamado.id}/mensagens',
                {'conteudo': 'Arquivos inválidos.', 'anexo': arquivos}, format='multipart')
            self.assertEqual(resultado.status_code, 400)
        self.assertFalse(self.chamado.mensagens.exists())
        self.assertFalse(Anexo.objects.exists())

    def test_upload_failure_rolls_back_message_files_and_notifications(self):
        antes = Notificacao.objects.count()
        with patch('chamados.models.Anexo.save', side_effect=DatabaseError('simulada')):
            with self.assertRaises(DatabaseError):
                services.enviar_mensagem(self.usuario, self.chamado.id, 'Anexo com falha', anexo=[self.pdf()])
        self.assertFalse(self.chamado.mensagens.exists())
        self.assertEqual(Notificacao.objects.count(), antes)
        self.assertFalse(any(p.is_file() for p in Path(self.pasta_temporaria.name).rglob('*')))

    def test_notifications_unread_and_isolated_per_user(self):
        services.enviar_mensagem(self.admin, self.chamado.id, 'Resposta da equipe.')
        self.autenticar(self.usuario)
        dados = self.api.get('/api/notificacoes').data
        self.assertGreater(dados['count'], 0)
        id = dados['results'][0]['id']
        self.autenticar(self.outra_pessoa)
        self.assertEqual(self.api.post(f'/api/notificacoes/{id}/ler').status_code, 404)
        self.autenticar(self.usuario)
        self.assertEqual(self.api.post(f'/api/notificacoes/{id}/ler').status_code, 204)
        self.assertIsNotNone(Notificacao.objects.get(pk=id).lida_em)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get('/notificacoes').status_code, 200)

    def test_internal_notifications_hidden_after_demotion(self):
        services.enviar_mensagem(self.admin, self.chamado.id, 'Nota para equipe', interna=True)
        self.assertTrue(fluxo.notificacoes_visiveis(self.tecnico).filter(interna=True).exists())
        self.tecnico.perfil = 'USER'
        self.tecnico.save()
        self.assertFalse(fluxo.notificacoes_visiveis(self.tecnico).exists())

    def test_duplicate_resolution_notifies_each_owner_without_leaking_incident(self):
        filho = services.criar_chamado(self.outra_pessoa, {'assunto': 'Mesmo problema',
            'descricao': 'A rede da outra sala também caiu.', 'urgencia': 'HIGH'})
        fluxo.vincular(self.admin, filho.id, self.chamado)
        services.enviar_mensagem(self.admin, self.chamado.id, 'INFORMAÇÃO RESTRITA', interna=True)
        self.resolver()
        filho.refresh_from_db()
        self.assertEqual(filho.status, 'RESOLVED')
        self.assertTrue(filho.solucao)
        self.assertTrue(Notificacao.objects.filter(chamado=filho, usuario=self.outra_pessoa, interna=False).exists())
        self.autenticar(self.outra_pessoa)
        self.assertEqual(self.api.get(f'/api/chamados/{self.chamado.id}').status_code, 404)
        detalhes = self.api.get(f'/api/chamados/{filho.id}').data
        self.assertNotIn('incidenteId', detalhes)
        self.assertNotIn('INFORMAÇÃO RESTRITA', str(detalhes))
        self.assertNotIn(self.chamado.assunto, str(detalhes))

    def test_duplicate_cycles_and_chains_rejected(self):
        filho = services.criar_chamado(self.outra_pessoa, {'assunto': 'Filho', 'descricao': 'Descrição do filho.', 'urgencia': 'LOW'})
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, self.chamado.id, self.chamado)
        fluxo.vincular(self.admin, filho.id, self.chamado)
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, self.chamado.id, filho)
        terceiro = services.criar_chamado(self.usuario, {'assunto': 'Terceiro', 'descricao': 'Descrição do terceiro.', 'urgencia': 'LOW'})
        with self.assertRaises(ValidationError):
            fluxo.vincular(self.admin, terceiro.id, filho)
        fluxo.vincular(self.admin, filho.id, None)
        filho.refresh_from_db()
        self.assertIsNone(filho.incidente_id)

    def test_management_and_workflow_api(self):
        self.autenticar(self.admin)
        r = self.api.patch(f'/api/chamados/{self.chamado.id}/gestao',
            {'responsavel': str(self.tecnico.pk)}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['responsavel']['id'], str(self.tecnico.pk))
        r = self.api.patch(f'/api/chamados/{self.chamado.id}/status',
            {'status': 'RESOLVED', 'solucao': 'Funcionamento restaurado e verificado.'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.autenticar(self.usuario)
        self.assertEqual(self.api.post(f'/api/chamados/{self.chamado.id}/confirmar').status_code, 200)
        r = self.api.post(f'/api/chamados/{self.chamado.id}/reabrir', {'motivo': 'Falha voltou a acontecer.'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.api.get(f'/api/chamados/{self.chamado.id}/historico').status_code, 200)

    def test_api_pagination_limits_tickets_and_messages(self):
        Chamado.objects.bulk_create([Chamado(usuario=self.usuario, assunto=f'Extra {i}',
            descricao='Descrição válida.', urgencia='LOW') for i in range(25)])
        MensagemChamado.objects.bulk_create([MensagemChamado(chamado=self.chamado, autor=self.usuario,
            conteudo=f'Mensagem {i}') for i in range(35)])
        self.autenticar(self.usuario)
        r = self.api.get('/api/chamados').data
        self.assertEqual(r['count'], 26)
        self.assertEqual(len(r['results']), 20)
        self.assertEqual(len(self.api.get('/api/chamados?page=2').data['results']), 6)
        detalhes = self.api.get(f'/api/chamados/{self.chamado.id}').data
        self.assertEqual(len(detalhes['mensagens']), 30)
        self.assertEqual(detalhes['mensagensTotal'], 35)
        self.assertEqual(len(self.api.get(f'/api/chamados/{self.chamado.id}/mensagens?page=2').data['results']), 5)

    def test_dashboard_filters_and_get_has_no_workflow_side_effect(self):
        fluxo.gerenciar(self.admin, self.chamado.id, {'responsavel': self.admin})
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/admin', {'meus': '1', 'categoria': self.categoria.pk}), self.chamado.assunto)
        self.assertNotContains(self.client.get('/admin', {'fila': 'sem'}), self.chamado.assunto)
        self.assertEqual(self.client.get(f'/tickets/{self.chamado.id}/acoes/confirmar').status_code, 405)
        self.assertEqual(self.client.get(f'/tickets/{self.chamado.id}').status_code, 200)

    def test_portal_management_preserves_second_precision_for_unchanged_dates(self):
        self.client.force_login(self.admin)
        dados = {'responsavel': str(self.tecnico.pk), 'categoria': self.categoria.pk, 'urgencia': 'HIGH',
            'prazo_resposta': timezone.localtime(self.chamado.prazo_resposta).strftime('%Y-%m-%dT%H:%M'),
            'prazo_resolucao': timezone.localtime(self.chamado.prazo_resolucao).strftime('%Y-%m-%dT%H:%M')}
        r = self.client.post(f'/tickets/{self.chamado.id}/acoes/gerenciar', dados)
        self.assertEqual(r.status_code, 302)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.responsavel, self.tecnico)
