import os
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from chamados.models import Usuario


class Command(BaseCommand):
    help = 'Cria o administrador inicial; só atualiza senha existente com --atualizar-senha.'

    def add_arguments(self, analisador):
        analisador.add_argument('--email')
        analisador.add_argument('--nome')
        analisador.add_argument('--atualizar-senha', action='store_true')

    def handle(self, *args, **opcoes):
        email = (opcoes['email'] or os.getenv('INITIAL_ADMIN_EMAIL') or input('E-mail do administrador: ')).strip().lower()
        nome = opcoes['nome'] or os.getenv('INITIAL_ADMIN_NAME') or input('Nome: ') or 'Administrador'
        senha = os.getenv('INITIAL_ADMIN_PASSWORD') or getpass('Senha (não será exibida): ')
        usuario = Usuario.objects.filter(email=email).first()
        if usuario and usuario.excluido_em is not None:
            raise CommandError('Esta conta foi excluída. Use outro e-mail para criar um administrador.')
        if usuario and not opcoes['atualizar_senha']:
            raise CommandError('Conta já existe. Use --atualizar-senha para alterar explicitamente.')
        usuario = usuario or Usuario(email=email)
        usuario.nome = nome
        try:
            validate_password(senha, usuario)
            usuario.set_password(senha)
            usuario.perfil = 'ADMIN'
            usuario.is_staff = True
            usuario.is_superuser = True
            usuario.is_active = True
            usuario.full_clean(exclude=['last_login'])
        except ValidationError as excecao:
            raise CommandError('; '.join(excecao.messages))
        usuario.save()
        self.stdout.write(self.style.SUCCESS('Administrador configurado. Acesse /login.'))
