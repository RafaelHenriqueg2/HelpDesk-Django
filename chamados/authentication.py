"""Valida tokens da API e consulta a situação atual da conta no banco."""
import uuid
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario

class AutenticacaoToken(BaseAuthentication):
    def authenticate_header(self, requisicao):
        return 'Bearer'

    def authenticate(self, requisicao):
        cabecalho = requisicao.headers.get('Authorization', '').split()
        if not cabecalho:
            return None
        if len(cabecalho) != 2 or cabecalho[0].lower() != 'bearer':
            raise AuthenticationFailed('Token inválido.')
        try:
            conteudo_token = jwt.decode(cabecalho[1], settings.SECRET_KEY, algorithms=['HS256'],
                options={'require': ['exp', 'iat', 'sub']})
            id = uuid.UUID(conteudo_token['sub'])
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
            raise AuthenticationFailed('Token inválido ou expirado.')
        # Um token antigo não devolve acesso a uma conta desativada ou excluída.
        usuario = Usuario.objects.filter(pk=id, is_active=True, excluido_em__isnull=True).first()
        if usuario is None:
            raise AuthenticationFailed('Conta indisponível.')
        return usuario, conteudo_token
