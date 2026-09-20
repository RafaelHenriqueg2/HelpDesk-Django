import uuid
from datetime import timedelta
from pathlib import Path
from django.db import models
from django.db.models.functions import Lower
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Informe o e-mail.')
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(role='ADMIN', is_staff=True, is_superuser=True, is_active=True)
        extra.setdefault('name', 'Administrador')
        return self.create_user(email, password, **extra)

class Usuario(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        USER = 'USER', 'Usuário'
        ADMIN = 'ADMIN', 'Administrador'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('nome', max_length=120)
    email = models.EmailField('e-mail', max_length=180, unique=True)
    role = models.CharField('perfil', max_length=5, choices=Role.choices, default=Role.USER)
    is_active = models.BooleanField('ativo', default=True)
    is_staff = models.BooleanField('acesso ao Django Admin', default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField('excluído em', null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey('self', verbose_name='excluído por', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='usuarios_excluidos', editable=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']
    objects = UsuarioManager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(Lower('email'), name='usuario_email_lower_unique'),
            models.CheckConstraint(condition=models.Q(deleted_at__isnull=True) | models.Q(is_active=False),
                name='usuario_excluido_inativo'),
        ]

    @property
    def is_admin(self):
        return self.is_active and self.deleted_at is None and (self.role == self.Role.ADMIN or self.is_superuser)

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.email})'

class ChamadoQuerySet(models.QuerySet):
    def permitidos(self, usuario):
        return self if usuario.is_admin else self.filter(usuario=usuario)


class Categoria(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Chamado(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Aberto'
        IN_PROGRESS = 'IN_PROGRESS', 'Em atendimento'
        RESOLVED = 'RESOLVED', 'Resolvido'
        WAITING_USER = 'WAITING_USER', 'Aguardando usuário'
        WAITING_THIRD = 'WAITING_THIRD', 'Aguardando terceiro'
        CLOSED = 'CLOSED', 'Encerrado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    class Urgencia(models.TextChoices):
        LOW = 'LOW', 'Baixa'
        MEDIUM = 'MEDIUM', 'Média'
        HIGH = 'HIGH', 'Alta'
        CRITICAL = 'CRITICAL', 'Crítica'

    # O banco gera o sequencial atomicamente; não usamos count()+1.
    numero = models.BigAutoField(primary_key=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    assunto = models.CharField(max_length=150)
    descricao = models.TextField()
    urgencia = models.CharField(max_length=8, choices=Urgencia.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN, db_index=True)
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
    objects = ChamadoQuerySet.as_manager()

    class Meta:
        ordering = ['-criado_em', '-numero']

    @property
    def protocolo(self):
        return f'HD-{self.numero:06d}'

    @property
    def finalizado(self):
        return self.status in (self.Status.RESOLVED, self.Status.CLOSED, self.Status.CANCELLED)

    @property
    def situacao_prazo(self):
        if self.finalizado:
            return 'Finalizado'
        agora = self.pausa_iniciada_em or timezone.now()
        prazos = [self.prazo_resolucao]
        if self.primeira_resposta_em is None:
            prazos.append(self.prazo_resposta)
        prazos = [p for p in prazos if p is not None]
        if prazos and min(prazos) < agora:
            return 'Atrasado (pausado)' if self.pausa_iniciada_em else 'Atrasado'
        if self.pausa_iniciada_em:
            return 'Pausado'
        if prazos and min(prazos) <= agora + timedelta(hours=1):
            return 'Vence em até 1 hora'
        return 'No prazo' if prazos else 'Sem prazo'

    def __str__(self):
        return f'{self.protocolo} — {self.assunto}'

def caminho_anexo(instance, filename):
    return f'anexos/{uuid.uuid4()}{Path(filename).suffix.lower()}'

class Anexo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='anexos')
    arquivo = models.FileField(upload_to=caminho_anexo)
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
    anterior = models.CharField(max_length=24, choices=Chamado.Status.choices)
    novo = models.CharField(max_length=24, choices=Chamado.Status.choices)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['criado_em', 'pk']


class EventoChamado(models.Model):
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
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='notificacoes')
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='notificacoes')
    titulo = models.CharField(max_length=200)
    interna = models.BooleanField(default=False)
    lida_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em', '-pk']
        indexes = [models.Index(fields=['usuario', 'lida_em', 'chamado'])]
