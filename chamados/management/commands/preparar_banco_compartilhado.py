from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Prepara schema privado PostgreSQL sem excluir tabelas nem dados.'

    def handle(self, *args, **opcoes):
        if connection.vendor != 'postgresql' or not settings.DATABASE_SCHEMA:
            raise CommandError('Configure PostgreSQL e DATABASE_SCHEMA antes de continuar.')
        nome = settings.DATABASE_SCHEMA
        if nome in ('public', 'auth', 'storage', 'extensions'):
            raise CommandError('Use um schema exclusivo do HelpDesk, como helpdesk.')
        esquema = connection.ops.quote_name(nome)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS {esquema}')
            cursor.execute(f'REVOKE ALL ON SCHEMA {esquema} FROM PUBLIC')
            for perfil in ('anon', 'authenticated'):
                cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [perfil])
                if cursor.fetchone():
                    cursor.execute(f'REVOKE ALL ON SCHEMA {esquema} FROM {connection.ops.quote_name(perfil)}')
                    cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA {esquema} FROM {connection.ops.quote_name(perfil)}')
                    cursor.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} REVOKE ALL ON TABLES FROM {connection.ops.quote_name(perfil)}')
        self.stdout.write(self.style.SUCCESS('Schema privado preparado. Execute migrate neste ambiente.'))
