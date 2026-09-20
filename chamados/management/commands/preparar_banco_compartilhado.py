from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Prepara schema privado PostgreSQL sem excluir tabelas nem dados.'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql' or not settings.DATABASE_SCHEMA:
            raise CommandError('Configure PostgreSQL e DATABASE_SCHEMA antes de continuar.')
        nome = settings.DATABASE_SCHEMA
        if nome in ('public', 'auth', 'storage', 'extensions'):
            raise CommandError('Use um schema exclusivo do HelpDesk, como helpdesk.')
        schema = connection.ops.quote_name(nome)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS {schema}')
            cursor.execute(f'REVOKE ALL ON SCHEMA {schema} FROM PUBLIC')
            for role in ('anon', 'authenticated'):
                cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [role])
                if cursor.fetchone():
                    cursor.execute(f'REVOKE ALL ON SCHEMA {schema} FROM {connection.ops.quote_name(role)}')
                    cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {connection.ops.quote_name(role)}')
                    cursor.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON TABLES FROM {connection.ops.quote_name(role)}')
        self.stdout.write(self.style.SUCCESS('Schema privado preparado. Execute migrate neste ambiente.'))
