"""Fluxos de atendimento usados pelo portal e pela API."""
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import (Usuario, Chamado, Categoria, Anexo, MensagemChamado,
    HistoricoStatus, EventoChamado, Notificacao)


def tecnicos():
    return Usuario.objects.filter(is_active=True, deleted_at__isnull=True).filter(
        Q(role=Usuario.Role.ADMIN) | Q(is_superuser=True))


def notificar(chamado, autor, titulo, interna=False, adicionais=()):
    ids = set(tecnicos().values_list('pk', flat=True))
    if not interna:
        ids.add(chamado.usuario_id)
    ids.update(adicionais)
    destinatarios = Usuario.objects.filter(pk__in=ids, is_active=True, deleted_at__isnull=True)
    if autor:
        destinatarios = destinatarios.exclude(pk=autor.pk)
    Notificacao.objects.bulk_create([Notificacao(usuario=u, chamado=chamado,
        titulo=titulo[:200], interna=interna) for u in destinatarios])


def evento(chamado, autor, campo, anterior='', novo='', motivo='', interno=False):
    EventoChamado.objects.create(chamado=chamado, autor=autor, campo=campo,
        anterior=str(anterior or ''), novo=str(novo or ''), motivo=motivo, interno=interno)


def definir_prazos(chamado, agora=None):
    agora = agora or timezone.now()
    resposta, resolucao = settings.SLA_HORAS[chamado.urgencia]
    chamado.prazo_resposta = agora + timedelta(hours=resposta)
    chamado.prazo_resolucao = agora + timedelta(hours=resolucao)


def retomar_prazos(chamado, agora):
    if chamado.pausa_iniciada_em:
        pausa = max(agora - chamado.pausa_iniciada_em, timedelta())
        if chamado.prazo_resposta and chamado.primeira_resposta_em is None:
            chamado.prazo_resposta += pausa
        if chamado.prazo_resolucao:
            chamado.prazo_resolucao += pausa
        chamado.segundos_pausados += int(pausa.total_seconds())
        chamado.pausa_iniciada_em = None


def mensagens_visiveis(chamado, usuario):
    qs = chamado.mensagens.select_related('autor').prefetch_related('anexos')
    return qs if usuario.is_admin else qs.filter(interna=False)


def anexos_visiveis(chamado, usuario):
    qs = chamado.anexos.select_related('mensagem')
    return qs if usuario.is_admin else qs.filter(Q(mensagem__isnull=True) | Q(mensagem__interna=False))


def eventos_visiveis(chamado, usuario):
    qs = chamado.eventos.select_related('autor')
    return qs if usuario.is_admin else qs.filter(interno=False)


def notificacoes_visiveis(usuario):
    qs = Notificacao.objects.filter(usuario=usuario,
        chamado__in=Chamado.objects.permitidos(usuario)).select_related('chamado')
    return qs if usuario.is_admin else qs.filter(interna=False)


def marcar_lidas(usuario, chamado):
    notificacoes_visiveis(usuario).filter(chamado=chamado, lida_em__isnull=True).update(lida_em=timezone.now())


def validar_arquivos(arquivos):
    from .forms import validar_anexo
    if not arquivos:
        return []
    arquivos = arquivos if isinstance(arquivos, (list, tuple)) else [arquivos]
    if len(arquivos) > 5 or sum(a.size for a in arquivos) > 20 * 1024 * 1024:
        raise ValidationError('Envie até 5 arquivos, somando no máximo 20 MB.')
    for arquivo in arquivos:
        validar_anexo(arquivo)
    return arquivos


def guardar_arquivos(chamado, arquivos, salvos, mensagem=None):
    for arquivo in arquivos:
        anexo = Anexo(chamado=chamado, mensagem=mensagem, nome=arquivo.name[:255],
            tipo=arquivo.content_type, tamanho=arquivo.size)
        anexo.arquivo.save(arquivo.name, arquivo, save=False)
        salvos.append(anexo)
        anexo.save()


def limpar_arquivos(salvos):
    for anexo in salvos:
        anexo.arquivo.delete(save=False)


def criar(usuario, dados):
    arquivos = validar_arquivos(dados.get('anexo'))
    salvos = []
    try:
        with transaction.atomic():
            categoria = dados.get('categoria') or Categoria.objects.get_or_create(nome='Outros')[0]
            if not categoria.ativa:
                raise ValidationError('Categoria indisponível.')
            chamado = Chamado(usuario=usuario, assunto=dados['assunto'],
                descricao=dados['descricao'], urgencia=dados['urgencia'], categoria=categoria)
            definir_prazos(chamado)
            chamado.save()
            guardar_arquivos(chamado, arquivos, salvos)
            evento(chamado, usuario, 'Abertura', novo='Chamado aberto')
            notificar(chamado, usuario, 'Novo chamado')
            return chamado
    except Exception:
        limpar_arquivos(salvos)
        raise


def _mudar_status(chamado, autor, novo, motivo='', solucao=''):
    agora = timezone.now()
    anterior = chamado.status
    if anterior == novo:
        return
    retomar_prazos(chamado, agora)
    if novo == Chamado.Status.WAITING_USER:
        chamado.pausa_iniciada_em = agora
    if novo == Chamado.Status.RESOLVED:
        chamado.solucao = solucao.strip()
        chamado.resolvido_em = agora
        # A solução pública também é uma primeira resposta.
        if chamado.primeira_resposta_em is None:
            chamado.primeira_resposta_em = agora
        chamado.confirmado_em = None
        evento(chamado, autor, 'Solução', novo=chamado.solucao)
    elif novo == Chamado.Status.CLOSED:
        chamado.confirmado_em = agora
    elif chamado.finalizado and novo == Chamado.Status.OPEN:
        chamado.solucao = ''
        chamado.resolvido_em = None
        chamado.confirmado_em = None
        chamado.primeira_resposta_em = None
        chamado.segundos_pausados = 0
        definir_prazos(chamado, agora)
        evento(chamado, autor, 'Prazos', novo='Novo ciclo de atendimento', motivo=motivo)
    elif novo not in (Chamado.Status.RESOLVED, Chamado.Status.CLOSED):
        chamado.resolvido_em = None
        chamado.confirmado_em = None
    chamado.status = novo
    chamado.save()
    HistoricoStatus.objects.create(chamado=chamado, autor=autor, anterior=anterior, novo=novo)
    nomes = dict(Chamado.Status.choices)
    evento(chamado, autor, 'Status', nomes[anterior], nomes[novo], motivo)
    notificar(chamado, autor, 'Status: ' + nomes[novo])


@transaction.atomic
def mudar_status(usuario, id, novo, solucao='', motivo=''):
    if not usuario.is_admin:
        raise PermissionDenied
    if novo not in Chamado.Status.values:
        raise ValidationError('Status inválido.')
    # Same lock order as linking, before acquiring any ticket row.
    list(tecnicos().select_for_update().order_by('pk'))
    chamado = get_object_or_404(Chamado.objects.select_for_update(), id=id)
    if novo == chamado.status:
        return chamado
    if novo == Chamado.Status.CLOSED:
        raise ValidationError('O encerramento deve ser confirmado pelo solicitante.')
    if chamado.finalizado and novo != Chamado.Status.OPEN:
        raise ValidationError('Reabra o chamado antes de alterar seu atendimento.')
    if novo == Chamado.Status.RESOLVED and len(solucao.strip()) < 10:
        raise ValidationError('Descreva a solução com pelo menos 10 caracteres.')
    if (novo == Chamado.Status.CANCELLED or chamado.finalizado) and len(motivo.strip()) < 5:
        raise ValidationError('Informe o motivo com pelo menos 5 caracteres.')
    _mudar_status(chamado, usuario, novo, motivo, solucao)
    if novo == Chamado.Status.RESOLVED:
        # Only direct children: linking rejects chains and cycles.
        filhos = chamado.duplicados.select_for_update().exclude(status__in=[
            Chamado.Status.RESOLVED, Chamado.Status.CLOSED, Chamado.Status.CANCELLED]).order_by('numero')
        for filho in filhos:
            MensagemChamado.objects.create(chamado=filho, autor=usuario,
                conteudo='Solução do incidente relacionado: ' + solucao.strip())
            _mudar_status(filho, usuario, Chamado.Status.RESOLVED,
                'Solução aplicada ao incidente relacionado.', solucao)
    return chamado


@transaction.atomic
def confirmar(usuario, id):
    chamado = get_object_or_404(Chamado.objects.select_for_update(), id=id, usuario=usuario)
    if chamado.status != Chamado.Status.RESOLVED:
        raise ValidationError('Somente um chamado resolvido pode ser confirmado.')
    _mudar_status(chamado, usuario, Chamado.Status.CLOSED, 'Solução confirmada pelo solicitante.')
    return chamado


@transaction.atomic
def reabrir(usuario, id, motivo):
    chamado = get_object_or_404(Chamado.objects.permitidos(usuario).select_for_update(), id=id)
    if chamado.status not in (Chamado.Status.RESOLVED, Chamado.Status.CLOSED):
        raise ValidationError('Somente chamados resolvidos ou encerrados podem ser reabertos.')
    if len(motivo.strip()) < 5:
        raise ValidationError('Explique o que ainda não funciona com pelo menos 5 caracteres.')
    _mudar_status(chamado, usuario, Chamado.Status.OPEN, motivo)
    MensagemChamado.objects.create(chamado=chamado, autor=usuario, conteudo='Reabertura: ' + motivo.strip())
    return chamado


def mensagem(usuario, id, conteudo, interna=False, arquivos=None):
    if interna and not usuario.is_admin:
        raise PermissionDenied('Notas internas são exclusivas da equipe.')
    arquivos = validar_arquivos(arquivos)
    if not conteudo.strip() or len(conteudo) > 2000:
        raise ValidationError('Escreva uma mensagem de até 2000 caracteres.')
    salvos = []
    try:
        with transaction.atomic():
            chamado = get_object_or_404(Chamado.objects.permitidos(usuario).select_for_update(), id=id)
            if chamado.status in (Chamado.Status.CLOSED, Chamado.Status.CANCELLED):
                raise ValidationError('Reabra o chamado antes de enviar uma mensagem.')
            msg = MensagemChamado.objects.create(chamado=chamado, autor=usuario,
                conteudo=conteudo, interna=interna)
            guardar_arquivos(chamado, arquivos, salvos, msg)
            if usuario.is_admin and usuario.pk != chamado.usuario_id and not interna and chamado.primeira_resposta_em is None:
                chamado.primeira_resposta_em = timezone.now()
            if usuario.pk == chamado.usuario_id and not interna and chamado.status == Chamado.Status.WAITING_USER:
                _mudar_status(chamado, usuario, Chamado.Status.IN_PROGRESS, 'Solicitante respondeu.')
            chamado.save()
            evento(chamado, usuario, 'Nota interna' if interna else 'Mensagem',
                novo='Mensagem enviada' + (f' com {len(arquivos)} anexo(s)' if arquivos else ''), interno=interna)
            notificar(chamado, usuario, 'Nova nota interna' if interna else 'Nova mensagem', interna=interna)
            return msg
    except Exception:
        limpar_arquivos(salvos)
        raise


@transaction.atomic
def gerenciar(usuario, id, dados):
    if not usuario.is_admin:
        raise PermissionDenied
    chamado = get_object_or_404(Chamado.objects.select_for_update(), id=id)
    if chamado.finalizado:
        raise ValidationError('Reabra o chamado antes de alterar o atendimento.')
    motivo = dados.get('motivo', '').strip()
    campos = {'responsavel': 'Responsável', 'categoria': 'Categoria', 'urgencia': 'Urgência',
        'prazo_resposta': 'Prazo de resposta', 'prazo_resolucao': 'Prazo de resolução'}
    extras, alterados = set(), []
    for campo, rotulo in campos.items():
        if campo not in dados:
            continue
        valor = dados[campo]
        anterior = getattr(chamado, campo)
        if campo.startswith('prazo_') and anterior and valor and anterior.replace(second=0, microsecond=0) == valor.replace(second=0, microsecond=0):
            continue
        if anterior == valor:
            continue
        if campo == 'responsavel' and valor and not tecnicos().filter(pk=valor.pk).exists():
            raise ValidationError('Selecione um técnico ativo.')
        if campo == 'categoria' and (valor is None or not Categoria.objects.filter(pk=valor.pk, ativa=True).exists()):
            raise ValidationError('Selecione uma categoria ativa.')
        if campo == 'urgencia' and valor not in Chamado.Urgencia.values:
            raise ValidationError('Urgência inválida.')
        if campo.startswith('prazo_'):
            if not valor or not motivo:
                raise ValidationError('Informe o prazo e justifique sua alteração.')
            if chamado.pausa_iniciada_em:
                raise ValidationError('Retome o atendimento antes de alterar os prazos.')
        if campo == 'responsavel' and anterior:
            extras.add(anterior.pk)
        setattr(chamado, campo, valor)
        evento(chamado, usuario, rotulo, anterior, valor, motivo)
        alterados.append(rotulo)
    if alterados:
        # Changing urgency does not silently erase an overdue deadline.
        chamado.save()
        notificar(chamado, usuario, 'Atendimento atualizado: ' + ', '.join(alterados), adicionais=extras)
    return chamado


@transaction.atomic
def vincular(usuario, id, incidente):
    if not usuario.is_admin:
        raise PermissionDenied
    # Serialize link changes to prevent simultaneous reciprocal links on PostgreSQL.
    list(Usuario.objects.select_for_update().filter(is_active=True).filter(
        Q(role='ADMIN') | Q(is_superuser=True)).order_by('pk'))
    chamado = get_object_or_404(Chamado.objects.select_for_update(), id=id)
    if incidente:
        incidente = get_object_or_404(Chamado.objects.select_for_update(), pk=incidente.pk)
        if chamado.pk == incidente.pk or incidente.incidente_id or chamado.duplicados.exists():
            raise ValidationError('Escolha um incidente principal diferente; cadeias e ciclos não são permitidos.')
        if incidente.finalizado or chamado.finalizado:
            raise ValidationError('Vincule apenas chamados em atendimento.')
    anterior = chamado.incidente
    if anterior == incidente:
        return chamado
    chamado.incidente = incidente
    chamado.save()
    evento(chamado, usuario, 'Incidente relacionado', anterior.protocolo if anterior else '',
        incidente.protocolo if incidente else '', interno=True)
    notificar(chamado, usuario, 'Vínculo de incidente atualizado', interna=True)
    return chamado
