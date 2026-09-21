"""Entrada WSGI para o servidor que hospeda a aplicação.

O nome application é mantido conforme a integração com o Django e o servidor.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biblioteca.settings')

application = get_wsgi_application()
