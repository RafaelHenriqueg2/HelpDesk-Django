import secrets
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from chamados.models import Usuario
from chamados import services


class Command(BaseCommand):
    help = 'Cria contas e chamados fictícios locais, com senhas aleatórias exibidas uma vez.'

    @transaction.atomic
    def handle(self, *args, **opcoes):
        if not settings.DEBUG:
            raise CommandError('A demonstração só pode ser criada com DEBUG=True.')
        emails = ['admin@helpdesk.local', 'usuario@helpdesk.local']
        if Usuario.objects.filter(email__in=emails).exists():
            raise CommandError('Contas de demonstração já existem; nenhuma senha foi alterada.')
        senha_administrador = secrets.token_urlsafe(16)
        senha_usuario = secrets.token_urlsafe(16)
        administrador = Usuario.objects.create_superuser(emails[0], senha_administrador, nome='Equipe de Suporte')
        usuario = Usuario.objects.create_user(emails[1], senha_usuario, nome='Mariana Oliveira')
        exemplos = [
            ('Não consigo acessar o sistema', 'Ao informar meu e-mail, o sistema mostra uma mensagem de erro. Preciso de ajuda para acessar.', 'HIGH', 'OPEN'),
            ('Impressora do laboratório offline', 'A impressora do laboratório aparece como offline em todos os computadores.', 'MEDIUM', 'IN_PROGRESS'),
            ('Instalação de ferramenta de estudo', 'Solicito a instalação da ferramenta necessária para a próxima aula de programação.', 'LOW', 'RESOLVED'),
        ]
        for assunto, descricao, urgencia, status in exemplos:
            chamado = services.criar_chamado(usuario, {'assunto': assunto, 'descricao': descricao, 'urgencia': urgencia})
            if status != 'OPEN':
                services.alterar_status(administrador, chamado.id, status,
                    solucao='Ferramenta instalada e funcionamento verificado com o solicitante.')
                services.enviar_mensagem(administrador, chamado.id, 'Recebemos sua solicitação e atualizamos o atendimento. Acompanhe por aqui.')
        self.stdout.write(self.style.SUCCESS('Demonstração criada. Guarde estas senhas:'))
        self.stdout.write(f'Administrador: {emails[0]} | senha: {senha_administrador}')
        self.stdout.write(f'Usuário: {emails[1]} | senha: {senha_usuario}')
