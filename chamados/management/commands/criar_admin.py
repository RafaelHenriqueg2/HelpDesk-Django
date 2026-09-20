import os
from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from chamados.models import Usuario


class Command(BaseCommand):
    help = 'Cria o administrador inicial; só atualiza senha existente com --atualizar-senha.'

    def add_arguments(self, parser):
        parser.add_argument('--email')
        parser.add_argument('--nome')
        parser.add_argument('--atualizar-senha', action='store_true')

    def handle(self, *args, **options):
        email = (options['email'] or os.getenv('INITIAL_ADMIN_EMAIL') or input('E-mail do administrador: ')).strip().lower()
        nome = options['nome'] or os.getenv('INITIAL_ADMIN_NAME') or input('Nome: ') or 'Administrador'
        senha = os.getenv('INITIAL_ADMIN_PASSWORD') or getpass('Senha (não será exibida): ')
        user = Usuario.objects.filter(email=email).first()
        if user and user.deleted_at is not None:
            raise CommandError('Esta conta foi excluída. Use outro e-mail para criar um administrador.')
        if user and not options['atualizar_senha']:
            raise CommandError('Conta já existe. Use --atualizar-senha para alterar explicitamente.')
        user = user or Usuario(email=email)
        user.name = nome
        try:
            validate_password(senha, user)
            user.set_password(senha)
            user.role = 'ADMIN'
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.full_clean(exclude=['last_login'])
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        user.save()
        self.stdout.write(self.style.SUCCESS('Administrador configurado. Acesse /login.'))
