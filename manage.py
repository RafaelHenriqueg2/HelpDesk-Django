#!/usr/bin/env python
"""Entrada dos comandos de administração: servidor, migrations e testes."""
import os
import sys


def principal():
    """Carrega as configurações e encaminha os argumentos para o Django."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biblioteca.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as excecao:
        raise ImportError(
            'Não foi possível importar o Django. Instale as dependências e '
            'execute este comando com o Python do ambiente virtual do projeto.'
        ) from excecao
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    principal()
