"""Regressões da tradução: compatibilidade externa e preservação dos dados."""
import io
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from .forms import FormularioEntrada, FormularioUsuario
from .models import Chamado, Usuario


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TestesNomesPortugues(TestCase):
    def test_cadastro_em_portugues_protege_senha(self):
        formulario = FormularioUsuario(data={'nome': 'Pessoa de Teste',
            'email': 'pessoa@test.local', 'perfil': 'USER', 'senha': 'SenhaForte!4729'})
        self.assertTrue(formulario.is_valid(), formulario.errors)
        usuario = formulario.save()
        self.assertEqual(usuario.nome, 'Pessoa de Teste')
        self.assertEqual(usuario.perfil, Usuario.Perfil.USUARIO)
        self.assertTrue(usuario.check_password('SenhaForte!4729'))
        self.assertNotEqual(usuario.password, 'SenhaForte!4729')

    def test_formulario_aceita_campos_anteriores(self):
        formulario = FormularioUsuario({'name': 'Cadastro Antigo', 'email': 'antigo@test.local',
            'role': 'ADMIN', 'password': 'SenhaAntiga!4729'})
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertTrue(formulario.save().eh_administrador)
        entrada = FormularioEntrada({'email': 'antigo@test.local', 'password': 'SenhaAntiga!4729'})
        self.assertTrue(entrada.is_valid())
        self.assertEqual(entrada.cleaned_data['senha'], 'SenhaAntiga!4729')

    def test_login_portugues_e_campos_visiveis_no_portal(self):
        usuario = Usuario.objects.create_superuser('admin@test.local', 'SenhaForte!4729', nome='Administrador')
        resposta = self.client.get('/login')
        self.assertContains(resposta, 'id="id_senha"')
        resposta = self.client.post('/login', {'email': usuario.email, 'senha': 'SenhaForte!4729'})
        self.assertEqual(resposta.status_code, 302)
        resposta = self.client.get('/admin/users')
        for campo in ('nome', 'perfil', 'senha'):
            self.assertContains(resposta, f'name="{campo}"')
        self.assertContains(resposta, 'aria-hidden="true">*</span>', count=4)
        self.assertContains(resposta, 'Administrador')

    def test_paginacao_html_preserva_numero_e_filtros(self):
        usuario = Usuario.objects.create_user('paginacao@test.local', nome='Solicitante')
        self.client.force_login(usuario)
        Chamado.objects.bulk_create([Chamado(usuario=usuario, assunto=f'Busca {indice}',
            descricao='Descrição para a consulta.', urgencia='LOW') for indice in range(21)])
        resposta = self.client.get('/home', {'q': 'Busca'})
        self.assertContains(resposta, 'q=Busca&amp;page=2')
        resposta = self.client.get('/home', {'q': 'Busca', 'page': 2})
        self.assertEqual(len(resposta.context['pagina']), 1)

    def test_comando_django_cria_superusuario_com_nome(self):
        call_command('createsuperuser', email='comando@test.local', nome='Administrador Inicial',
            interactive=False, stdout=io.StringIO())
        usuario = Usuario.objects.get(email='comando@test.local')
        self.assertEqual(usuario.nome, 'Administrador Inicial')
        self.assertTrue(usuario.eh_administrador)


class TestesMigracaoPortugues(TransactionTestCase):
    def test_renomeacao_preserva_contas_excluidas_e_historico(self):
        anterior = [('chamados', '0004_preparar_categorias_prazos')]
        atual = [('chamados', '0005_identificadores_portugues')]
        executor = MigrationExecutor(connection)
        executor.migrate(anterior)
        try:
            aplicativos = executor.loader.project_state(anterior).apps
            ContaAnterior = aplicativos.get_model('chamados', 'Usuario')
            ChamadoAnterior = aplicativos.get_model('chamados', 'Chamado')
            autor = ContaAnterior.objects.create(email='autor@migracao.local', name='Administrador', role='ADMIN')
            instante = timezone.now()
            excluido = ContaAnterior.objects.create(email='excluido@migracao.local', name='Conta Excluída',
                role='USER', is_active=False, deleted_at=instante, deleted_by=autor, password='!inutilizavel')
            chamado = ChamadoAnterior.objects.create(usuario=excluido, assunto='Histórico mantido',
                descricao='Solicitação anterior à migração.', urgencia='HIGH', responsavel=autor)
            MigrationExecutor(connection).migrate(atual)
            conta = Usuario.objects.get(pk=excluido.pk)
            self.assertEqual(conta.nome, 'Conta Excluída')
            self.assertEqual(conta.perfil, 'USER')
            self.assertEqual(conta.excluido_em, instante)
            self.assertEqual(conta.excluido_por_id, autor.pk)
            self.assertEqual(conta.criado_em, excluido.created_at)
            self.assertEqual(conta.atualizado_em, excluido.updated_at)
            self.assertEqual(conta.password, '!inutilizavel')
            self.assertFalse(conta.eh_administrador)
            self.assertEqual(Chamado.objects.get(pk=chamado.pk).usuario_id, excluido.pk)
            # A reversão também é não destrutiva, permitindo recuperar a versão anterior.
            MigrationExecutor(connection).migrate(anterior)
            restaurado = ContaAnterior.objects.get(pk=excluido.pk)
            self.assertEqual(restaurado.name, 'Conta Excluída')
            self.assertEqual(restaurado.deleted_by_id, autor.pk)
        finally:
            MigrationExecutor(connection).migrate(atual)
