"""Entrada ASGI para o servidor que hospeda a aplicação.

O nome application é mantido conforme a integração com o Django e o servidor.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biblioteca.settings')

application = get_asgi_application()
