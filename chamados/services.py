"""Regras compartilhadas pelas views HTML e pela API."""
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Usuario, Chamado, RegistroLogin
from . import fluxo

def entrar(requisicao, email, senha):
    """Autentica e registra a tentativa sem armazenar a senha informada."""
    email = email.strip().lower()
    usuario = Usuario.objects.filter(email=email).first()
    autenticado = authenticate(requisicao, username=email, password=senha)
    motivo = ''
    if autenticado is None:
        motivo = ('USUARIO_NAO_ENCONTRADO' if usuario is None else
            'USUARIO_DESATIVADO' if not usuario.is_active else 'SENHA_INVALIDA')
    RegistroLogin.objects.create(usuario=usuario, email_informado=email[:180],
        sucesso=autenticado is not None, motivo_falha=motivo,
        endereco_ip=requisicao.META.get('REMOTE_ADDR', '')[:64],
        agente_usuario=requisicao.META.get('HTTP_USER_AGENT', '')[:500])
    return autenticado

def consultar(usuario):
    return Chamado.objects.permitidos(usuario).select_related('usuario', 'categoria', 'responsavel')


def usuarios_disponiveis():
    # O gerenciador padrão inclui excluídos para manter os vínculos do histórico.
    # A lista do portal aplica este filtro específico para esconder essas contas.
    return Usuario.objects.filter(excluido_em__isnull=True)


def pode_excluir_usuario(autor, alvo):
    return (autor.eh_administrador and autor.pk != alvo.pk and alvo.excluido_em is None
        and (autor.is_superuser or not (alvo.is_superuser or alvo.is_staff)))


@transaction.atomic
def excluir_usuario(autor, id):
    # Bloqueia as duas contas na mesma ordem e confere novamente o administrador.
    # Isso evita exclusões simultâneas com permissões desatualizadas na sessão.
    contas = {conta.pk: conta for conta in Usuario.objects.select_for_update().filter(
        pk__in=[autor.pk, id]).order_by('pk')}
    atual = contas.get(autor.pk)
    if atual is None or not atual.eh_administrador:
        raise PermissionDenied
    alvo = contas.get(id)
    if alvo is None or alvo.excluido_em is not None:
        raise Http404('Usuário não encontrado.')
    if atual.pk == alvo.pk:
        raise ValidationError('Você não pode excluir sua própria conta.')
    if not pode_excluir_usuario(atual, alvo):
        raise PermissionDenied('Somente um superusuário pode excluir uma conta com acesso técnico.')
    alvo.is_active = False
    # Desativa o acesso e a senha sem apagar mensagens ou chamados relacionados.
    alvo.excluido_em = timezone.now()
    alvo.excluido_por = atual
    alvo.set_unusable_password()
    alvo.save(update_fields=['is_active', 'excluido_em', 'excluido_por', 'password', 'atualizado_em'])
    return alvo

def buscar(usuario, id):
    return get_object_or_404(consultar(usuario), id=id)

def criar_chamado(usuario, dados):
    return fluxo.criar(usuario, dados)

def alterar_status(usuario, id, status, solucao='', motivo=''):
    return fluxo.mudar_status(usuario, id, status, solucao, motivo)

def enviar_mensagem(usuario, id, conteudo, interna=False, anexo=None):
    return fluxo.mensagem(usuario, id, conteudo, interna, anexo)

def baixar_anexo(usuario, id, anexo_id):
    """Entrega o arquivo somente depois de conferir acesso ao chamado e à nota."""
    chamado = buscar(usuario, id)
    anexo = get_object_or_404(fluxo.anexos_visiveis(chamado, usuario), pk=anexo_id)
    try:
        arquivo = anexo.arquivo.open('rb')
    except FileNotFoundError:
        raise Http404('Arquivo não encontrado.')
    resposta = FileResponse(arquivo, as_attachment=True, filename=anexo.nome, content_type=anexo.tipo)
    resposta['Cache-Control'] = 'private, no-store'
    return resposta
