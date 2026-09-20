import uuid
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario

class BearerAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def authenticate(self, request):
        header = request.headers.get('Authorization', '').split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != 'bearer':
            raise AuthenticationFailed('Token invÃ¡lido.')
        try:
            payload = jwt.decode(header[1], settings.SECRET_KEY, algorithms=['HS256'],
                options={'require': ['exp', 'iat', 'sub']})
            id = uuid.UUID(payload['sub'])
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
            raise AuthenticationFailed('Token invÃ¡lido ou expirado.')
        usuario = Usuario.objects.filter(pk=id, is_active=True, deleted_at__isnull=True).first()
        if usuario is None:
            raise AuthenticationFailed('Conta indisponÃ­vel.')
        return usuario, payload
