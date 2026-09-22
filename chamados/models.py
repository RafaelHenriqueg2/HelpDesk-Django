"""Estruturas persistidas no banco e regras simples de cada registro."""
import uuid
from datetime import timedelta
from pathlib import Path
from django.db import models
from django.db.models.functions import Lower
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class GerenciadorUsuarios(BaseUserManager):
    """Cria contas com e-mail normalizado e senha protegida por hash."""

    # Estes nomes são pontos de integração do Django, inclusive createsuperuser.
    use_in_migrations = True

    def create_user(self, email, password=None, **campos_adicionais):
        if not email:
            raise ValueError('Informe o e-mail.')
        usuario = self.model(email=email.strip().lower(), **campos_adicionais)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **campos_adicionais):
        campos_adicionais.update(perfil='ADMIN', is_staff=True, is_superuser=True, is_active=True)
        campos_adicionais.setdefault('nome', 'Administrador')
        return self.create_user(email, password, **campos_adicionais)

class Usuario(AbstractBaseUser, PermissionsMixin):
    """Conta de acesso; a exclusão lógica conserva os atendimentos antigos."""
    class Perfil(models.TextChoices):
        USUARIO = 'USER', 'Usuário'
        ADMINISTRADOR = 'ADMIN', 'Administrador'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField('nome', max_length=120)
    email = models.EmailField('e-mail', max_length=180, unique=True)
    perfil = models.CharField('perfil', max_length=5, choices=Perfil.choices, default=Perfil.USUARIO)
    is_active = models.BooleanField('ativo', default=True)
    is_staff = models.BooleanField('acesso ao Django Admin', default=False)
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)
    excluido_em = models.DateTimeField('excluído em', null=True, blank=True, db_index=True)
    excluido_por = models.ForeignKey('self', verbose_name='excluído por', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='usuarios_excluidos', editable=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nome']
    objects = GerenciadorUsuarios()

    class Meta:
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(Lower('email'), name='usuario_email_lower_unique'),
            models.CheckConstraint(condition=models.Q(excluido_em__isnull=True) | models.Q(is_active=False),
                name='usuario_excluido_inativo'),
        ]

    @property
    def eh_administrador(self):
        # A permissão considera a situação atual da conta, não apenas o perfil.
        return self.is_active and self.excluido_em is None and (self.perfil == self.Perfil.ADMINISTRADOR or self.is_superuser)

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nome} ({self.email})'

class ConsultaChamados(models.QuerySet):
    """Centraliza a restrição de chamados por solicitante."""
    def permitidos(self, usuario):
        return self if usuario.eh_administrador else self.filter(usuario=usuario)


class Categoria(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Chamado(models.Model):
    """Solicitação de suporte com responsável, situação e prazos de atendimento."""

    # Os nomes Python são traduzidos; os códigos gravados e usados na API são estáveis.
    class Situacao(models.TextChoices):
        ABERTO = 'OPEN', 'Aberto'
        EM_ATENDIMENTO = 'IN_PROGRESS', 'Em atendimento'
        RESOLVIDO = 'RESOLVED', 'Resolvido'
        AGUARDANDO_USUARIO = 'WAITING_USER', 'Aguardando usuário'
        AGUARDANDO_TERCEIRO = 'WAITING_THIRD', 'Aguardando terceiro'
        ENCERRADO = 'CLOSED', 'Encerrado'
        CANCELADO = 'CANCELLED', 'Cancelado'

    class Urgencia(models.TextChoices):
        BAIXA = 'LOW', 'Baixa'
        MEDIA = 'MEDIUM', 'Média'
        ALTA = 'HIGH', 'Alta'
        CRITICA = 'CRITICAL', 'Crítica'

    # O banco gera o sequencial atomicamente; não usamos count()+1.
    numero = models.BigAutoField(primary_key=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    assunto = models.CharField(max_length=150)
    descricao = models.TextField()
    urgencia = models.CharField(max_length=8, choices=Urgencia.choices)
    status = models.CharField(max_length=24, choices=Situacao.choices, default=Situacao.ABERTO, db_index=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='chamados')
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    categoria = models.ForeignKey(Categoria, null=True, blank=True, on_delete=models.PROTECT)
    responsavel = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT,
        related_name='atendimentos')
    incidente = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='duplicados')
    solucao = models.TextField(blank=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    primeira_resposta_em = models.DateTimeField(null=True, blank=True)
    prazo_resposta = models.DateTimeField(null=True, blank=True, db_index=True)
    prazo_resolucao = models.DateTimeField(null=True, blank=True, db_index=True)
    pausa_iniciada_em = models.DateTimeField(null=True, blank=True)
    segundos_pausados = models.PositiveBigIntegerField(default=0)
    objects = ConsultaChamados.as_manager()

    class Meta:
        ordering = ['-criado_em', '-numero']

    @property
    def protocolo(self):
        return f'HD-{self.numero:06d}'

    @property
    def finalizado(self):
        return self.status in (self.Situacao.RESOLVIDO, self.Situacao.ENCERRADO, self.Situacao.CANCELADO)

    @property
    def situacao_prazo(self):
        # Durante a pausa, avalia o atraso no instante em que o relógio parou.
        if self.finalizado:
            return 'Finalizado'
        agora = self.pausa_iniciada_em or timezone.now()
        prazos = [self.prazo_resolucao]
        if self.primeira_resposta_em is None:
            prazos.append(self.prazo_resposta)
        prazos = [prazo for prazo in prazos if prazo is not None]
        if prazos and min(prazos) < agora:
            return 'Atrasado (pausado)' if self.pausa_iniciada_em else 'Atrasado'
        if self.pausa_iniciada_em:
            return 'Pausado'
        if prazos and min(prazos) <= agora + timedelta(hours=1):
            return 'Vence em até 1 hora'
        return 'No prazo' if prazos else 'Sem prazo'

    def __str__(self):
        return f'{self.protocolo} — {self.assunto}'

def caminho_anexo(instancia, nome_arquivo):
    # Um nome aleatório evita colisões e não revela o nome original na pasta.
    return f'anexos/{uuid.uuid4()}{Path(nome_arquivo).suffix.lower()}'

class Anexo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='anexos')
    # O conteúdo fica no próprio banco. Base64 permite exportar e restaurar o
    # registro completo sem depender de uma pasta ou serviço de arquivos.
    conteudo_base64 = models.TextField(editable=False)
    nome = models.CharField(max_length=255)
    tipo = models.CharField(max_length=120)
    tamanho = models.PositiveIntegerField()
    criado_em = models.DateTimeField(default=timezone.now)
    mensagem = models.ForeignKey('MensagemChamado', null=True, blank=True,
        on_delete=models.CASCADE, related_name='anexos')

class MensagemChamado(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='mensagens')
    autor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    conteudo = models.TextField()
    interna = models.BooleanField(default=False)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['criado_em', 'id']
        indexes = [models.Index(fields=['chamado', 'criado_em'])]

class RegistroLogin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    email_informado = models.CharField(max_length=180)
    sucesso = models.BooleanField()
    endereco_ip = models.CharField(max_length=64, blank=True)
    agente_usuario = models.CharField(max_length=500, blank=True)
    motivo_falha = models.CharField(max_length=120, blank=True)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-criado_em']

class HistoricoStatus(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='historico')
    autor = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    anterior = models.CharField(max_length=24, choices=Chamado.Situacao.choices)
    novo = models.CharField(max_length=24, choices=Chamado.Situacao.choices)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['criado_em', 'pk']


class EventoChamado(models.Model):
    """Auditoria das alterações; eventos internos são visíveis somente à equipe."""
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='eventos')
    autor = models.ForeignKey(Usuario, null=True, on_delete=models.PROTECT)
    campo = models.CharField(max_length=40)
    anterior = models.TextField(blank=True)
    novo = models.TextField(blank=True)
    motivo = models.TextField(blank=True)
    interno = models.BooleanField(default=False)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em', '-pk']


class Notificacao(models.Model):
    """Aviso por destinatário, com leitura independente de outros usuários."""
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='notificacoes')
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='notificacoes')
    titulo = models.CharField(max_length=200)
    interna = models.BooleanField(default=False)
    lida_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em', '-pk']
        indexes = [models.Index(fields=['usuario', 'lida_em', 'chamado'])]

# O nome antigo permanece somente para carregar a migration 0001 já distribuída.
UsuarioManager = GerenciadorUsuarios
