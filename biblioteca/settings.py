"""Configura banco, autenticação, páginas e armazenamento do HelpDesk."""
import os
import secrets
import json
import re
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
# Arquivos locais guardam segredos; o repositório inclui somente exemplos vazios.
load_dotenv(os.getenv('HELPDESK_ENV_FILE') or BASE_DIR / '.env')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Defina SECRET_KEY em produção.')
    # Preserva a chave entre reinicializações para manter as sessões locais válidas.
    caminho_segredo = BASE_DIR / '.django-secret'
    try:
        with caminho_segredo.open('x', encoding='utf-8') as arquivo_segredo:
            arquivo_segredo.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = caminho_segredo.read_text(encoding='utf-8').strip()
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'chamados',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'biblioteca.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'chamados.context_processors.notificacoes',
    ]},
}]
WSGI_APPLICATION = 'biblioteca.wsgi.application'
ASGI_APPLICATION = 'biblioteca.asgi.application'
SHARED_DATABASE = os.getenv('SHARED_DATABASE', 'False').lower() == 'true'
# Os nomes das configurações e das variáveis de ambiente são interfaces estáveis.
DATABASE_SCHEMA = os.getenv('DATABASE_SCHEMA', '')
if SHARED_DATABASE and not os.getenv('DATABASE_URL'):
    raise ImproperlyConfigured('Defina DATABASE_URL para usar o banco compartilhado.')
if SHARED_DATABASE and not os.getenv('SECRET_KEY'):
    raise ImproperlyConfigured('Use a mesma SECRET_KEY nas instâncias que compartilham o banco.')
DATABASES = {'default': dj_database_url.parse(os.getenv('DATABASE_URL') or
    'sqlite:///' + str(BASE_DIR / 'db.sqlite3'), conn_max_age=0)}
if SHARED_DATABASE and DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('O banco compartilhado deve usar PostgreSQL.')
if DATABASE_SCHEMA:
    # Um esquema exclusivo separa as tabelas do portal das APIs públicas do provedor.
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', DATABASE_SCHEMA) or DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
        raise ImproperlyConfigured('DATABASE_SCHEMA deve ser um identificador PostgreSQL válido.')
    DATABASES['default'].setdefault('OPTIONS', {})['options'] = '-c search_path=' + DATABASE_SCHEMA
if SHARED_DATABASE:
    DATABASES['default'].setdefault('OPTIONS', {}).setdefault('sslmode', 'require')
    if DATABASES['default']['OPTIONS']['sslmode'] not in ('require', 'verify-ca', 'verify-full'):
        raise ImproperlyConfigured('O banco compartilhado exige uma conexão TLS.')
AUTH_USER_MODEL = 'chamados.Usuario'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Não publicar esta pasta como /media/: o download exige autorização.
MEDIA_ROOT = BASE_DIR / 'private_uploads'
if os.getenv('STORAGE_S3_ENDPOINT'):
    # O armazenamento remoto guarda anexos privados; o portal controla o download.
    for campo in ['STORAGE_S3_KEY', 'STORAGE_S3_SECRET', 'STORAGE_S3_REGION', 'STORAGE_S3_BUCKET']:
        if not os.getenv(campo):
            raise ImproperlyConfigured('Configuração incompleta do armazenamento privado: ' + campo)
    if not os.environ['STORAGE_S3_ENDPOINT'].startswith('https://'):
        raise ImproperlyConfigured('O armazenamento compartilhado exige HTTPS.')
    STORAGES = {
        'default': {'BACKEND': 'chamados.storage.ArmazenamentoPrivadoS3', 'OPTIONS': {
            'endpoint_url': os.environ['STORAGE_S3_ENDPOINT'],
            'access_key': os.environ['STORAGE_S3_KEY'],
            'secret_key': os.environ['STORAGE_S3_SECRET'],
            'region_name': os.environ['STORAGE_S3_REGION'],
            'bucket_name': os.environ['STORAGE_S3_BUCKET'],
            'addressing_style': 'path', 'signature_version': 's3v4',
            'default_acl': None, 'file_overwrite': False,
            'max_memory_size': 5 * 1024 * 1024,
            'object_parameters': {'CacheControl': 'private, no-store'},
        }},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login'
SESSION_COOKIE_AGE = 28800
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = list(filter(None, os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')))
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
JWT_EXPIRES_SECONDS = int(os.getenv('JWT_EXPIRES_SECONDS', '28800'))
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['chamados.authentication.AutenticacaoToken'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'EXCEPTION_HANDLER': 'chamados.api.tratar_excecao',
}

# Horas corridas: primeira resposta, resolução. Aguardando usuário pausa a contagem.
SLA_HORAS = json.loads(os.getenv('SLA_HORAS_JSON',
    '{"LOW":[24,72],"MEDIUM":[8,24],"HIGH":[2,8],"CRITICAL":[0.5,4]}'))
if set(SLA_HORAS) != {'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'} or any(
    not isinstance(v, list) or len(v) != 2 or any(not isinstance(n, (int, float)) or n <= 0 for n in v)
    for v in SLA_HORAS.values()):
    raise ImproperlyConfigured('SLA_HORAS_JSON deve definir dois prazos positivos para cada urgência.')
