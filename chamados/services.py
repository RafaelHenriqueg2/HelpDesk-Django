"""Regras compartilhadas pelas views HTML e pela API."""
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Usuario, Chamado, Anexo, MensagemChamado, RegistroLogin, HistoricoStatus
from . import fluxo

def entrar(request, email, password):
    email = email.strip().lower()
    usuario = Usuario.objects.filter(email=email).first()
    autenticado = authenticate(request, username=email, password=password)
    motivo = ''
    if autenticado is None:
        motivo = ('USUARIO_NAO_ENCONTRADO' if usuario is None else
            'USUARIO_DESATIVADO' if not usuario.is_active else 'SENHA_INVALIDA')
    RegistroLogin.objects.create(usuario=usuario, email_informado=email[:180],
        sucesso=autenticado is not None, motivo_falha=motivo,
        endereco_ip=request.META.get('REMOTE_ADDR', '')[:64],
        agente_usuario=request.META.get('HTTP_USER_AGENT', '')[:500])
    return autenticado

def consultar(usuario):
    return Chamado.objects.permitidos(usuario).select_related('usuario', 'categoria', 'responsavel')


def usuarios_disponiveis():
    # Keep the default manager unfiltered so historical foreign keys still resolve.
    return Usuario.objects.filter(deleted_at__isnull=True)


def pode_excluir_usuario(autor, alvo):
    return (autor.is_admin and autor.pk != alvo.pk and alvo.deleted_at is None
        and (autor.is_superuser or not (alvo.is_superuser or alvo.is_staff)))


@transaction.atomic
def excluir_usuario(autor, id):
    # Lock both accounts in a stable order and recheck the actor: concurrent
    # administrators must not exclude each other using stale sessions.
    contas = {u.pk: u for u in Usuario.objects.select_for_update().filter(
        pk__in=[autor.pk, id]).order_by('pk')}
    atual = contas.get(autor.pk)
    if atual is None or not atual.is_admin:
        raise PermissionDenied
    alvo = contas.get(id)
    if alvo is None or alvo.deleted_at is not None:
        raise Http404('Usuário não encontrado.')
    if atual.pk == alvo.pk:
        raise ValidationError('Você não pode excluir sua própria conta.')
    if not pode_excluir_usuario(atual, alvo):
        raise PermissionDenied('Somente um superusuário pode excluir uma conta com acesso técnico.')
    alvo.is_active = False
    alvo.deleted_at = timezone.now()
    alvo.deleted_by = atual
    alvo.set_unusable_password()
    alvo.save(update_fields=['is_active', 'deleted_at', 'deleted_by', 'password', 'updated_at'])
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
    chamado = buscar(usuario, id)
    anexo = get_object_or_404(fluxo.anexos_visiveis(chamado, usuario), pk=anexo_id)
    try:
        arquivo = anexo.arquivo.open('rb')
    except FileNotFoundError:
        raise Http404('Arquivo não encontrado.')
    resposta = FileResponse(arquivo, as_attachment=True, filename=anexo.nome, content_type=anexo.tipo)
    resposta['Cache-Control'] = 'private, no-store'
    return resposta
