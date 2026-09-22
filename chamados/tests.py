import base64
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from .models import Anexo, Categoria, Chamado, Usuario
from . import fluxo


def imagem_png():
    conteudo = BytesIO()
    Image.new('RGB', (2, 2), '#4563d5').save(conteudo, format='PNG')
    return conteudo.getvalue()


class AnexosNoBancoTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            'usuario@example.invalid', 'Senha-ficticia-2026!', nome='Usuário')
        self.outro = Usuario.objects.create_user(
            'outro@example.invalid', 'Senha-ficticia-2026!', nome='Outro')
        self.categoria = Categoria.objects.create(nome='Teste')

    def test_imagem_e_convertida_para_base64_e_baixada_com_o_mesmo_conteudo(self):
        original = imagem_png()
        imagem = SimpleUploadedFile('evidencia.png', original, content_type='image/png')
        chamado = fluxo.criar(self.usuario, {'assunto': 'Teste de imagem',
            'descricao': 'Descrição suficiente para criar o chamado.',
            'urgencia': Chamado.Urgencia.MEDIA, 'categoria': self.categoria, 'anexo': [imagem]})

        anexo = Anexo.objects.get(chamado=chamado)
        self.assertEqual(base64.b64decode(anexo.conteudo_base64), original)
        self.client.force_login(self.usuario)
        resposta = self.client.get(f'/tickets/{chamado.id}/anexos/{anexo.id}')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b''.join(resposta.streaming_content), original)

        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(
            f'/tickets/{chamado.id}/anexos/{anexo.id}').status_code, 404)


class IndicadoresDoUsuarioTests(TestCase):
    def test_usuario_ve_somente_os_quatro_indicadores_principais(self):
        usuario = Usuario.objects.create_user(
            'usuario@example.invalid', 'Senha-ficticia-2026!', nome='Usuário')
        self.client.force_login(usuario)
        resposta = self.client.get('/home')
        self.assertContains(resposta, 'Total')
        self.assertContains(resposta, 'Aberto')
        self.assertContains(resposta, 'Em atendimento')
        self.assertContains(resposta, 'Resolvido')
        self.assertNotContains(resposta,
            '<article class="stat"><span>Aguardando usuário</span>')
        self.assertNotContains(resposta,
            '<article class="stat"><span>Aguardando terceiro</span>')
        self.assertNotContains(resposta,
            '<article class="stat"><span>Encerrado</span>')
        self.assertNotContains(resposta,
            '<article class="stat"><span>Cancelado</span>')
