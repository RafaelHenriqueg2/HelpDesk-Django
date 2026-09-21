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
from .forms import (FormularioEntrada, FormularioUsuario, FormularioChamado, FormularioSituacao, FormularioMensagem,
    FormularioGestao, FormularioReabertura, FormularioIncidente)
from . import services
from . import fluxo

def tratar_excecao(excecao, contexto):
    if isinstance(excecao, DjangoValidationError):
        excecao = ValidationError(excecao.messages)
    resposta = drf_exception_handler(excecao, contexto)
    if resposta is not None:
        dados = resposta.data
        if isinstance(dados, dict):
            mensagem = dados.get('detail') or [str(valor) for valores in dados.values() for valor in (valores if isinstance(valores, list) else [valores])]
        else:
            mensagem = dados
        resposta.data = {'statusCode': resposta.status_code, 'message': mensagem}
    return resposta

class PermissaoAdministrador(BasePermission):
    def has_permission(self, requisicao, funcao_pagina):
        return requisicao.user.is_authenticated and requisicao.user.eh_administrador

def usuario_json(usuario):
    # As chaves externas são preservadas para não quebrar clientes da API.
    return {'id': str(usuario.id), 'name': usuario.nome, 'email': usuario.email, 'role': usuario.perfil,
        'active': usuario.is_active, 'createdAt': usuario.criado_em.isoformat(), 'updatedAt': usuario.atualizado_em.isoformat()}

def mensagem_json(mensagem):
    return {'id': str(mensagem.id), 'conteudo': mensagem.conteudo, 'criadoEm': mensagem.criado_em.isoformat(),
        'interna': mensagem.interna, 'attachments': [anexo_json(anexo) for anexo in mensagem.anexos.all()],
        'autor': {'name': mensagem.autor.nome, 'role': mensagem.autor.perfil}}


def anexo_json(anexo):
    return {'id': str(anexo.id), 'fileName': anexo.nome, 'size': anexo.tamanho}


def pagina_json(requisicao, consulta, serializar, tamanho=20):
    pagina = Paginator(consulta, tamanho).get_page(requisicao.query_params.get('page'))
    return {'count': pagina.paginator.count, 'page': pagina.number,
        'nextPage': pagina.next_page_number() if pagina.has_next() else None,
        'previousPage': pagina.previous_page_number() if pagina.has_previous() else None,
        'results': [serializar(item) for item in pagina]}

def chamado_json(chamado, usuario, detalhado=False):
    dados = {'id': str(chamado.id), 'sequenceNumber': chamado.numero, 'subject': chamado.assunto,
        'description': chamado.descricao, 'urgency': chamado.urgencia, 'status': chamado.status,
        'createdAt': chamado.criado_em.isoformat(), 'updatedAt': chamado.atualizado_em.isoformat(),
        'user': {'name': chamado.usuario.nome, 'email': chamado.usuario.email},
        'categoria': {'id': chamado.categoria_id, 'nome': chamado.categoria.nome} if chamado.categoria_id else None,
        'responsavel': {'id': str(chamado.responsavel_id), 'name': chamado.responsavel.nome} if chamado.responsavel_id else None,
        'solucao': chamado.solucao, 'situacaoPrazo': chamado.situacao_prazo,
        'prazoResposta': chamado.prazo_resposta.isoformat() if chamado.prazo_resposta else None,
        'prazoResolucao': chamado.prazo_resolucao.isoformat() if chamado.prazo_resolucao else None,
        'attachments': [anexo_json(anexo) for anexo in fluxo.anexos_visiveis(chamado, usuario)]}
    if usuario.eh_administrador:
        dados['incidenteId'] = str(chamado.incidente.id) if chamado.incidente_id else None
    if detalhado:
        mensagens = fluxo.mensagens_visiveis(chamado, usuario)
        dados['mensagens'] = [mensagem_json(mensagem) for mensagem in mensagens.order_by('-criado_em', '-id')[:30]][::-1]
        dados['mensagensTotal'] = mensagens.count()
    return dados

def validar(classe_formulario, requisicao):
    if not hasattr(requisicao.data, 'items'):
        raise ValidationError('Envie um objeto com os campos esperados.')
    # QueryDict.copy faz deepcopy dos uploads temporários e falha em arquivos grandes.
    # Os arquivos seguem por requisicao.FILES; aqui copiamos somente os campos comuns.
    dados = {chave: valor for chave, valor in requisicao.data.items() if chave not in requisicao.FILES}
    if classe_formulario is FormularioUsuario and 'role' not in dados and 'perfil' not in dados:
        dados['role'] = 'USER'
    formulario = classe_formulario(dados, requisicao.FILES) if classe_formulario in (FormularioChamado, FormularioMensagem) else classe_formulario(dados)
    if not formulario.is_valid():
        raise ValidationError(dict(formulario.errors))
    return formulario

class AutenticacaoAPI(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def get_authenticate_header(self, requisicao):
        return 'Bearer'

    def post(self, requisicao):
        formulario = validar(FormularioEntrada, requisicao)
        usuario = services.entrar(requisicao, **formulario.cleaned_data)
        if usuario is None:
            raise AuthenticationFailed('E-mail ou senha inválidos.')
        agora = timezone.now()
        token = jwt.encode({'sub': str(usuario.id), 'email': usuario.email, 'role': usuario.perfil,
            'iat': agora, 'exp': agora + timedelta(seconds=settings.JWT_EXPIRES_SECONDS)},
            settings.SECRET_KEY, algorithm='HS256')
        return Response({'accessToken': token, 'user': usuario_json(usuario)})

class MinhaContaAPI(APIView):
    def get(self, requisicao):
        return Response(usuario_json(requisicao.user))

class UsuariosAPI(APIView):
    permission_classes = [PermissaoAdministrador]
    def get(self, requisicao):
        return Response(pagina_json(requisicao, services.usuarios_disponiveis(), usuario_json))
    def post(self, requisicao):
        formulario = validar(FormularioUsuario, requisicao)
        try:
            usuario = formulario.save()
        except IntegrityError:
            erro = APIException('Já existe um usuário com este e-mail.')
            erro.status_code = 409
            raise erro
        return Response(usuario_json(usuario), status=201)

class UsuarioAPI(APIView):
    permission_classes = [PermissaoAdministrador]
    def get(self, requisicao, id):
        return Response(usuario_json(get_object_or_404(services.usuarios_disponiveis(), pk=id)))

    def delete(self, requisicao, id):
        try:
            services.excluir_usuario(requisicao.user, id)
        except DjangoValidationError as erro:
            raise ValidationError(erro.messages)
        return Response(status=204)

class ChamadosAPI(APIView):
    def get(self, requisicao):
        consulta = services.consultar(requisicao.user)
        if requisicao.query_params.get('meus') == '1' and requisicao.user.eh_administrador:
            consulta = consulta.filter(responsavel=requisicao.user)
        if requisicao.query_params.get('status'):
            consulta = consulta.filter(status=requisicao.query_params['status'])
        if requisicao.query_params.get('urgencia'):
            consulta = consulta.filter(urgencia=requisicao.query_params['urgencia'])
        return Response(pagina_json(requisicao, consulta, lambda chamado: chamado_json(chamado, requisicao.user)))
    def post(self, requisicao):
        formulario = validar(FormularioChamado, requisicao)
        chamado = services.criar_chamado(requisicao.user, formulario.cleaned_data)
        return Response(chamado_json(chamado, requisicao.user), status=201)

class ChamadoAPI(APIView):
    def get(self, requisicao, id):
        return Response(chamado_json(services.buscar(requisicao.user, id), requisicao.user, True))

class SituacaoAPI(APIView):
    permission_classes = [PermissaoAdministrador]
    def patch(self, requisicao, id):
        formulario = validar(FormularioSituacao, requisicao)
        return Response(chamado_json(services.alterar_status(requisicao.user, id, **formulario.cleaned_data), requisicao.user))

class MensagemAPI(APIView):
    def get(self, requisicao, id):
        chamado = services.buscar(requisicao.user, id)
        return Response(pagina_json(requisicao, fluxo.mensagens_visiveis(chamado, requisicao.user).order_by(
            '-criado_em', '-id'), mensagem_json, 30))

    def post(self, requisicao, id):
        formulario = validar(FormularioMensagem, requisicao)
        return Response(mensagem_json(services.enviar_mensagem(requisicao.user, id,
            **formulario.cleaned_data)), status=201)


class CategoriaAPI(APIView):
    def get(self, requisicao):
        return Response([{'id': chamado.pk, 'nome': chamado.nome} for chamado in Categoria.objects.filter(ativa=True)])


class GestaoAPI(APIView):
    permission_classes = [PermissaoAdministrador]

    def patch(self, requisicao, id):
        chamado = services.buscar(requisicao.user, id)
        if not isinstance(requisicao.data, dict):
            raise ValidationError('Envie um objeto JSON.')
        # Valida o formulário completo, mas altera somente os campos enviados no PATCH.
        dados = {campo: getattr(chamado, campo + '_id') if campo in ('responsavel', 'categoria') else getattr(chamado, campo)
            for campo in ('responsavel', 'categoria', 'urgencia', 'prazo_resposta', 'prazo_resolucao')}
        dados.update(requisicao.data)
        formulario = FormularioGestao(dados)
        if not formulario.is_valid():
            raise ValidationError(dict(formulario.errors))
        alteracoes = {chave: valor for chave, valor in formulario.cleaned_data.items() if chave in requisicao.data}
        return Response(chamado_json(fluxo.gerenciar(requisicao.user, id, alteracoes), requisicao.user))


class ConfirmarAPI(APIView):
    def post(self, requisicao, id):
        return Response(chamado_json(fluxo.confirmar(requisicao.user, id), requisicao.user))


class ReabrirAPI(APIView):
    def post(self, requisicao, id):
        formulario = validar(FormularioReabertura, requisicao)
        return Response(chamado_json(fluxo.reabrir(requisicao.user, id, formulario.cleaned_data['motivo']), requisicao.user))


class IncidenteAPI(APIView):
    permission_classes = [PermissaoAdministrador]

    def patch(self, requisicao, id):
        chamado = services.buscar(requisicao.user, id)
        if not isinstance(requisicao.data, dict) or 'incidente' not in requisicao.data:
            raise ValidationError('Informe incidente (número sequencial) ou null para desvincular.')
        formulario = FormularioIncidente(requisicao.data, chamado=chamado)
        if not formulario.is_valid():
            raise ValidationError(dict(formulario.errors))
        return Response(chamado_json(fluxo.vincular(requisicao.user, id, formulario.cleaned_data['incidente']), requisicao.user))


class HistoricoAPI(APIView):
    def get(self, requisicao, id):
        chamado = services.buscar(requisicao.user, id)
        return Response(pagina_json(requisicao, fluxo.eventos_visiveis(chamado, requisicao.user),
            lambda evento: {'id': evento.pk, 'campo': evento.campo, 'anterior': evento.anterior, 'novo': evento.novo,
                'motivo': evento.motivo, 'interno': evento.interno, 'autor': evento.autor.nome if evento.autor else 'Sistema',
                'criadoEm': evento.criado_em.isoformat()}))


class NotificacoesAPI(APIView):
    def get(self, requisicao):
        return Response(pagina_json(requisicao, fluxo.notificacoes_visiveis(requisicao.user),
            lambda notificacao: {'id': notificacao.pk, 'chamadoId': str(notificacao.chamado.id), 'protocolo': notificacao.chamado.protocolo,
                'titulo': notificacao.titulo, 'lida': notificacao.lida_em is not None, 'criadoEm': notificacao.criado_em.isoformat()}))


class LerNotificacaoAPI(APIView):
    def post(self, requisicao, id):
        notificacao = get_object_or_404(fluxo.notificacoes_visiveis(requisicao.user), pk=id)
        notificacao.lida_em = timezone.now()
        notificacao.save(update_fields=['lida_em'])
        return Response(status=204)

class AnexoAPI(APIView):
    def get(self, requisicao, id, anexo_id):
        return services.baixar_anexo(requisicao.user, id, anexo_id)

class DisponibilidadeAPI(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def get(self, requisicao):
        inicio = timezone.now()
        banco_disponivel = True
        try:
            Usuario.objects.exists()
        except DatabaseError:
            banco_disponivel = False
        return Response({'servidorConectado': True, 'bancoConectado': banco_disponivel,
            'verificadoEm': timezone.now().isoformat(),
            'tempoRespostaMs': int((timezone.now() - inicio).total_seconds() * 1000)}, status=200 if banco_disponivel else 503)
