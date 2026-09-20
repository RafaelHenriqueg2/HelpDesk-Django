"""Contrato REST preservado: nomes de campos e rotas do NestJS original."""
import uuid
from datetime import timedelta
import jwt
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db import connection, DatabaseError, IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ValidationError, APIException
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler as drf_exception_handler
from .models import Usuario, Categoria
from .forms import (LoginForm, UsuarioForm, ChamadoForm, StatusForm, MensagemForm,
    GerenciarForm, ReabrirForm, IncidenteForm)
from . import services
from . import fluxo

def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.messages)
    response = drf_exception_handler(exc, context)
    if response is not None:
        data = response.data
        if isinstance(data, dict):
            message = data.get('detail') or [str(v) for values in data.values() for v in (values if isinstance(values, list) else [values])]
        else:
            message = data
        response.data = {'statusCode': response.status_code, 'message': message}
    return response

class AdminPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin

def usuario_json(user):
    return {'id': str(user.id), 'name': user.name, 'email': user.email, 'role': user.role,
        'active': user.is_active, 'createdAt': user.created_at.isoformat(), 'updatedAt': user.updated_at.isoformat()}

def mensagem_json(m):
    return {'id': str(m.id), 'conteudo': m.conteudo, 'criadoEm': m.criado_em.isoformat(),
        'interna': m.interna, 'attachments': [anexo_json(a) for a in m.anexos.all()],
        'autor': {'name': m.autor.name, 'role': m.autor.role}}


def anexo_json(a):
    return {'id': str(a.id), 'fileName': a.nome, 'size': a.tamanho}


def pagina_json(request, qs, serializar, tamanho=20):
    page = Paginator(qs, tamanho).get_page(request.query_params.get('page'))
    return {'count': page.paginator.count, 'page': page.number,
        'nextPage': page.next_page_number() if page.has_next() else None,
        'previousPage': page.previous_page_number() if page.has_previous() else None,
        'results': [serializar(item) for item in page]}

def chamado_json(c, usuario, detalhado=False):
    data = {'id': str(c.id), 'sequenceNumber': c.numero, 'subject': c.assunto,
        'description': c.descricao, 'urgency': c.urgencia, 'status': c.status,
        'createdAt': c.criado_em.isoformat(), 'updatedAt': c.atualizado_em.isoformat(),
        'user': {'name': c.usuario.name, 'email': c.usuario.email},
        'categoria': {'id': c.categoria_id, 'nome': c.categoria.nome} if c.categoria_id else None,
        'responsavel': {'id': str(c.responsavel_id), 'name': c.responsavel.name} if c.responsavel_id else None,
        'solucao': c.solucao, 'situacaoPrazo': c.situacao_prazo,
        'prazoResposta': c.prazo_resposta.isoformat() if c.prazo_resposta else None,
        'prazoResolucao': c.prazo_resolucao.isoformat() if c.prazo_resolucao else None,
        'attachments': [anexo_json(a) for a in fluxo.anexos_visiveis(c, usuario)]}
    if usuario.is_admin:
        data['incidenteId'] = str(c.incidente.id) if c.incidente_id else None
    if detalhado:
        mensagens = fluxo.mensagens_visiveis(c, usuario)
        data['mensagens'] = [mensagem_json(m) for m in mensagens.order_by('-criado_em', '-id')[:30]][::-1]
        data['mensagensTotal'] = mensagens.count()
    return data

def validar(form_class, request):
    if not hasattr(request.data, 'items'):
        raise ValidationError('Envie um objeto com os campos esperados.')
    # QueryDict.copy faz deepcopy dos uploads temporários e falha em arquivos grandes.
    # Os arquivos seguem por request.FILES; aqui copiamos somente os valores dos campos.
    data = {key: value for key, value in request.data.items() if key not in request.FILES}
    if form_class is UsuarioForm and 'role' not in data:
        data['role'] = 'USER'
    form = form_class(data, request.FILES) if form_class in (ChamadoForm, MensagemForm) else form_class(data)
    if not form.is_valid():
        raise ValidationError(dict(form.errors))
    return form

class LoginAPI(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def get_authenticate_header(self, request):
        return 'Bearer'

    def post(self, request):
        form = validar(LoginForm, request)
        user = services.entrar(request, **form.cleaned_data)
        if user is None:
            raise AuthenticationFailed('E-mail ou senha inválidos.')
        agora = timezone.now()
        token = jwt.encode({'sub': str(user.id), 'email': user.email, 'role': user.role,
            'iat': agora, 'exp': agora + timedelta(seconds=settings.JWT_EXPIRES_SECONDS)},
            settings.SECRET_KEY, algorithm='HS256')
        return Response({'accessToken': token, 'user': usuario_json(user)})

class MeAPI(APIView):
    def get(self, request):
        return Response(usuario_json(request.user))

class UsersAPI(APIView):
    permission_classes = [AdminPermission]
    def get(self, request):
        return Response(pagina_json(request, services.usuarios_disponiveis(), usuario_json))
    def post(self, request):
        form = validar(UsuarioForm, request)
        try:
            user = form.save()
        except IntegrityError:
            error = APIException('Já existe um usuário com este e-mail.')
            error.status_code = 409
            raise error
        return Response(usuario_json(user), status=201)

class UserAPI(APIView):
    permission_classes = [AdminPermission]
    def get(self, request, id):
        return Response(usuario_json(get_object_or_404(services.usuarios_disponiveis(), pk=id)))

    def delete(self, request, id):
        try:
            services.excluir_usuario(request.user, id)
        except DjangoValidationError as error:
            raise ValidationError(error.messages)
        return Response(status=204)

class ChamadosAPI(APIView):
    def get(self, request):
        qs = services.consultar(request.user)
        if request.query_params.get('meus') == '1' and request.user.is_admin:
            qs = qs.filter(responsavel=request.user)
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        if request.query_params.get('urgencia'):
            qs = qs.filter(urgencia=request.query_params['urgencia'])
        return Response(pagina_json(request, qs, lambda c: chamado_json(c, request.user)))
    def post(self, request):
        form = validar(ChamadoForm, request)
        chamado = services.criar_chamado(request.user, form.cleaned_data)
        return Response(chamado_json(chamado, request.user), status=201)

class ChamadoAPI(APIView):
    def get(self, request, id):
        return Response(chamado_json(services.buscar(request.user, id), request.user, True))

class StatusAPI(APIView):
    permission_classes = [AdminPermission]
    def patch(self, request, id):
        form = validar(StatusForm, request)
        return Response(chamado_json(services.alterar_status(request.user, id, **form.cleaned_data), request.user))

class MensagemAPI(APIView):
    def get(self, request, id):
        chamado = services.buscar(request.user, id)
        return Response(pagina_json(request, fluxo.mensagens_visiveis(chamado, request.user).order_by(
            '-criado_em', '-id'), mensagem_json, 30))

    def post(self, request, id):
        form = validar(MensagemForm, request)
        return Response(mensagem_json(services.enviar_mensagem(request.user, id,
            **form.cleaned_data)), status=201)


class CategoriaAPI(APIView):
    def get(self, request):
        return Response([{'id': c.pk, 'nome': c.nome} for c in Categoria.objects.filter(ativa=True)])


class GestaoAPI(APIView):
    permission_classes = [AdminPermission]

    def patch(self, request, id):
        chamado = services.buscar(request.user, id)
        if not isinstance(request.data, dict):
            raise ValidationError('Envie um objeto JSON.')
        # PATCH validates a complete form but only changes supplied fields.
        dados = {f: getattr(chamado, f + '_id') if f in ('responsavel', 'categoria') else getattr(chamado, f)
            for f in ('responsavel', 'categoria', 'urgencia', 'prazo_resposta', 'prazo_resolucao')}
        dados.update(request.data)
        form = GerenciarForm(dados)
        if not form.is_valid():
            raise ValidationError(dict(form.errors))
        changed = {k: v for k, v in form.cleaned_data.items() if k in request.data}
        return Response(chamado_json(fluxo.gerenciar(request.user, id, changed), request.user))


class ConfirmarAPI(APIView):
    def post(self, request, id):
        return Response(chamado_json(fluxo.confirmar(request.user, id), request.user))


class ReabrirAPI(APIView):
    def post(self, request, id):
        form = validar(ReabrirForm, request)
        return Response(chamado_json(fluxo.reabrir(request.user, id, form.cleaned_data['motivo']), request.user))


class IncidenteAPI(APIView):
    permission_classes = [AdminPermission]

    def patch(self, request, id):
        chamado = services.buscar(request.user, id)
        if not isinstance(request.data, dict) or 'incidente' not in request.data:
            raise ValidationError('Informe incidente (número sequencial) ou null para desvincular.')
        form = IncidenteForm(request.data, chamado=chamado)
        if not form.is_valid():
            raise ValidationError(dict(form.errors))
        return Response(chamado_json(fluxo.vincular(request.user, id, form.cleaned_data['incidente']), request.user))


class HistoricoAPI(APIView):
    def get(self, request, id):
        chamado = services.buscar(request.user, id)
        return Response(pagina_json(request, fluxo.eventos_visiveis(chamado, request.user),
            lambda e: {'id': e.pk, 'campo': e.campo, 'anterior': e.anterior, 'novo': e.novo,
                'motivo': e.motivo, 'interno': e.interno, 'autor': e.autor.name if e.autor else 'Sistema',
                'criadoEm': e.criado_em.isoformat()}))


class NotificacoesAPI(APIView):
    def get(self, request):
        return Response(pagina_json(request, fluxo.notificacoes_visiveis(request.user),
            lambda n: {'id': n.pk, 'chamadoId': str(n.chamado.id), 'protocolo': n.chamado.protocolo,
                'titulo': n.titulo, 'lida': n.lida_em is not None, 'criadoEm': n.criado_em.isoformat()}))


class LerNotificacaoAPI(APIView):
    def post(self, request, id):
        n = get_object_or_404(fluxo.notificacoes_visiveis(request.user), pk=id)
        n.lida_em = timezone.now()
        n.save(update_fields=['lida_em'])
        return Response(status=204)

class AnexoAPI(APIView):
    def get(self, request, id, anexo_id):
        return services.baixar_anexo(request.user, id, anexo_id)

class HealthAPI(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def get(self, request):
        inicio = timezone.now()
        ok = True
        try:
            Usuario.objects.exists()
        except DatabaseError:
            ok = False
        return Response({'servidorConectado': True, 'bancoConectado': ok,
            'verificadoEm': timezone.now().isoformat(),
            'tempoRespostaMs': int((timezone.now() - inicio).total_seconds() * 1000)}, status=200 if ok else 503)
