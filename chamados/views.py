"""Recebe os formulários do navegador e monta as páginas HTML do portal."""
from functools import wraps
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q, Exists, OuterRef
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_http_methods
from .forms import FormularioEntrada, FormularioUsuario, FormularioChamado, FormularioMensagem, FormularioSituacao
from .models import Chamado, RegistroLogin
from . import services
from . import fluxo
from .models import Categoria
from .forms import FormularioGestao, FormularioReabertura, FormularioIncidente

def exige_administrador(funcao_pagina):
    """Protege páginas administrativas antes de executar a ação solicitada."""
    @login_required
    @wraps(funcao_pagina)
    def verificar_permissao(requisicao, *args, **kwargs):
        if not requisicao.user.eh_administrador:
            raise PermissionDenied
        return funcao_pagina(requisicao, *args, **kwargs)
    return verificar_permissao

def inicio(requisicao):
    if not requisicao.user.is_authenticated:
        return redirect('login')
    return redirect('dashboard' if requisicao.user.eh_administrador else 'home')

@require_http_methods(['GET', 'POST'])
def entrar(requisicao):
    if requisicao.user.is_authenticated:
        return inicio(requisicao)
    formulario = FormularioEntrada(requisicao.POST or None)
    if requisicao.method == 'POST' and formulario.is_valid():
        usuario = services.entrar(requisicao, **formulario.cleaned_data)
        if usuario:
            login(requisicao, usuario)
            return inicio(requisicao)
        formulario.add_error(None, 'E-mail ou senha inválidos.')
    return render(requisicao, 'chamados/login.html', {'formulario': formulario})

@require_POST
def sair(requisicao):
    logout(requisicao)
    return redirect('login')

@login_required
def pagina_usuario(requisicao):
    return painel(requisicao)

@exige_administrador
def painel_administrativo(requisicao):
    return painel(requisicao)

def painel(requisicao):
    # Aplica as permissões antes de calcular indicadores, buscas e paginação.
    chamados = services.consultar(requisicao.user)
    contagem = dict(chamados.order_by().values('status').annotate(total=Count('numero')).values_list('status', 'total'))
    resumo = [{'status': codigo, 'rotulo': rotulo, 'total': contagem.get(codigo, 0)} for codigo, rotulo in Chamado.Situacao.choices]
    resumo_destaque = resumo if requisicao.user.eh_administrador else [
        item for item in resumo if item['status'] in (
            Chamado.Situacao.ABERTO, Chamado.Situacao.EM_ATENDIMENTO, Chamado.Situacao.RESOLVIDO)]
    busca = requisicao.GET.get('q', '').strip()
    status = requisicao.GET.get('status', '')
    categoria = requisicao.GET.get('categoria', '')
    urgencia = requisicao.GET.get('urgencia', '')
    meus = requisicao.GET.get('meus') == '1'
    fila = requisicao.GET.get('fila', '')
    prazo = requisicao.GET.get('prazo', '')
    if categoria.isdecimal() and len(categoria) < 10:
        chamados = chamados.filter(categoria_id=int(categoria))
    if urgencia in Chamado.Urgencia.values:
        chamados = chamados.filter(urgencia=urgencia)
    if requisicao.user.eh_administrador and meus:
        chamados = chamados.filter(responsavel=requisicao.user)
    if requisicao.user.eh_administrador and fila == 'sem':
        chamados = chamados.filter(responsavel__isnull=True)
    if prazo in ('atrasados', 'proximos'):
        agora = timezone.now()
        from datetime import timedelta
        limite = agora if prazo == 'atrasados' else agora + timedelta(hours=1)
        chamados = chamados.exclude(status__in=['RESOLVED', 'CLOSED', 'CANCELLED']).filter(
            pausa_iniciada_em__isnull=True).filter(Q(prazo_resolucao__lte=limite) |
            Q(primeira_resposta_em__isnull=True, prazo_resposta__lte=limite))
        if prazo == 'proximos':
            chamados = chamados.exclude(Q(prazo_resolucao__lt=agora) |
                Q(primeira_resposta_em__isnull=True, prazo_resposta__lt=agora))
    pendentes = fluxo.notificacoes_visiveis(requisicao.user).filter(
        chamado_id=OuterRef('pk'), lida_em__isnull=True)
    chamados = chamados.annotate(nao_lidas=Exists(pendentes))
    if requisicao.GET.get('nao_lidas') == '1':
        chamados = chamados.filter(nao_lidas=True)
    if status in Chamado.Situacao.values:
        chamados = chamados.filter(status=status)
    if busca:
        filtro = Q(assunto__icontains=busca)
        numero = busca.upper().removeprefix('HD-')
        if numero.isdecimal() and len(numero) <= 18:
            filtro |= Q(numero=int(numero))
        if requisicao.user.eh_administrador:
            filtro |= Q(usuario__nome__icontains=busca) | Q(usuario__email__icontains=busca)
        chamados = chamados.filter(filtro)
    return render(requisicao, 'chamados/lista.html', {'pagina': Paginator(chamados, 20).get_page(requisicao.GET.get('page')),
        'resumo': resumo, 'resumo_destaque': resumo_destaque,
        'total': sum(contagem.values()), 'busca': busca, 'status': status,
        'categorias': Categoria.objects.filter(ativa=True), 'categoria': categoria,
        'urgencias': Chamado.Urgencia.choices, 'urgencia': urgencia, 'meus': meus,
        'fila': fila, 'prazo': prazo, 'filtros': requisicao.GET})

@login_required
@require_http_methods(['GET', 'POST'])
def novo_chamado(requisicao):
    formulario = FormularioChamado(requisicao.POST or None, requisicao.FILES or None)
    if requisicao.method == 'POST' and formulario.is_valid():
        chamado = services.criar_chamado(requisicao.user, formulario.cleaned_data)
        messages.success(requisicao, f'Chamado enviado com sucesso. Protocolo {chamado.protocolo}.')
        return redirect('detalhe', id=chamado.id)
    return render(requisicao, 'chamados/form.html', {'formulario': formulario, 'titulo': 'Abrir novo chamado',
        'subtitulo': 'Conte o que aconteceu para nossa equipe ajudar você.', 'botao': 'Enviar chamado'})

@login_required
@require_http_methods(['GET', 'POST'])
def detalhe(requisicao, id):
    chamado = services.buscar(requisicao.user, id)
    formulario = FormularioMensagem(requisicao.POST or None, requisicao.FILES or None, usuario=requisicao.user)
    if requisicao.method == 'POST' and formulario.is_valid():
        try:
            services.enviar_mensagem(requisicao.user, id, **formulario.cleaned_data)
        except ValidationError as erro:
            formulario.add_error(None, erro)
        else:
            messages.success(requisicao, 'Mensagem enviada.')
            return redirect('detalhe', id=id)
    conversa = Paginator(fluxo.mensagens_visiveis(chamado, requisicao.user).order_by(
        '-criado_em', '-id'), 30).get_page(requisicao.GET.get('mensagens'))
    historico = Paginator(fluxo.eventos_visiveis(chamado, requisicao.user), 20).get_page(requisicao.GET.get('historico'))
    # Marca apenas avisos existentes antes da montagem desta resposta.
    corte = timezone.now()
    fluxo.notificacoes_visiveis(requisicao.user).filter(chamado=chamado,
        lida_em__isnull=True, criado_em__lte=corte).update(lida_em=corte)
    return render(requisicao, 'chamados/detalhe.html', {'chamado': chamado, 'formulario': formulario,
        'formulario_situacao': FormularioSituacao(initial={'status': chamado.status}, auto_id='status_%s'),
        'formulario_gestao': FormularioGestao(initial={campo: getattr(chamado, campo) for campo in
            ['responsavel', 'categoria', 'urgencia', 'prazo_resposta', 'prazo_resolucao']}, auto_id='gestao_%s'),
        'formulario_reabertura': FormularioReabertura(auto_id='reabrir_%s'), 'formulario_incidente': FormularioIncidente(chamado=chamado,
            initial={'incidente': chamado.incidente_id}, auto_id='incidente_%s'),
        'conversa': conversa, 'historico': historico,
        'anexos': fluxo.anexos_visiveis(chamado, requisicao.user).filter(mensagem__isnull=True),
        'duplicados': chamado.duplicados.all() if requisicao.user.eh_administrador else [],
        'pode_confirmar': chamado.usuario_id == requisicao.user.pk and chamado.status == 'RESOLVED',
        'pode_reabrir': chamado.status in ('RESOLVED', 'CLOSED')})

@exige_administrador
@require_POST
def alterar_situacao(requisicao, id):
    formulario = FormularioSituacao(requisicao.POST)
    if formulario.is_valid():
        try:
            services.alterar_status(requisicao.user, id, **formulario.cleaned_data)
        except ValidationError as erro:
            messages.error(requisicao, '; '.join(erro.messages))
        else:
            messages.success(requisicao, 'Situacao atualizado.')
    else:
        messages.error(requisicao, 'Situacao inválido.')
    return redirect('detalhe', id=id)

@login_required
def anexo(requisicao, id, anexo_id):
    return services.baixar_anexo(requisicao.user, id, anexo_id)

@exige_administrador
@require_http_methods(['GET', 'POST'])
def usuarios(requisicao):
    formulario = FormularioUsuario(requisicao.POST or None, initial={'perfil': 'USER'})
    if requisicao.method == 'POST' and formulario.is_valid():
        try:
            formulario.save()
        except IntegrityError:
            formulario.add_error('email', 'Já existe um usuário com este e-mail.')
        else:
            messages.success(requisicao, 'Usuário cadastrado com sucesso.')
            return redirect('usuarios')
    busca = requisicao.GET.get('q', '').strip()
    lista = services.usuarios_disponiveis()
    if busca:
        lista = lista.filter(Q(nome__icontains=busca) | Q(email__icontains=busca))
    pagina = Paginator(lista, 20).get_page(requisicao.GET.get('page'))
    for usuario in pagina:
        usuario.pode_excluir = services.pode_excluir_usuario(requisicao.user, usuario)
    return render(requisicao, 'chamados/usuarios.html', {'formulario': formulario, 'busca': busca, 'pagina': pagina})

@exige_administrador
def usuario_detalhe(requisicao, id):
    usuario = get_object_or_404(services.usuarios_disponiveis(), pk=id)
    return render(requisicao, 'chamados/usuario.html', {'usuario': usuario,
        'pode_excluir': services.pode_excluir_usuario(requisicao.user, usuario)})


@exige_administrador
@require_http_methods(['GET', 'POST'])
def usuario_excluir(requisicao, id):
    usuario = get_object_or_404(services.usuarios_disponiveis(), pk=id)
    if not services.pode_excluir_usuario(requisicao.user, usuario):
        raise PermissionDenied('Não é permitido excluir esta conta.')
    if requisicao.method == 'POST':
        if requisicao.POST.get('confirmar') != 'sim':
            messages.error(requisicao, 'Confirme a exclusão para continuar.')
        else:
            try:
                services.excluir_usuario(requisicao.user, id)
            except ValidationError as erro:
                messages.error(requisicao, erro.messages[0])
            else:
                messages.success(requisicao, f'Conta de {usuario.nome} excluída. O histórico foi preservado.')
                return redirect('usuarios')
    return render(requisicao, 'chamados/usuario_excluir.html', {'usuario': usuario})

@exige_administrador
def auditoria(requisicao):
    return render(requisicao, 'chamados/auditoria.html', {
        'pagina': Paginator(RegistroLogin.objects.all(), 30).get_page(requisicao.GET.get('page'))})


@login_required
@require_POST
def acao_chamado(requisicao, id, acao):
    chamado = services.buscar(requisicao.user, id)
    try:
        if acao == 'confirmar':
            fluxo.confirmar(requisicao.user, id)
        elif acao == 'reabrir':
            formulario = FormularioReabertura(requisicao.POST)
            if not formulario.is_valid():
                raise ValidationError('Explique o motivo da reabertura (5 a 2000 caracteres).')
            fluxo.reabrir(requisicao.user, id, formulario.cleaned_data['motivo'])
        elif acao in ('gerenciar', 'vincular'):
            if not requisicao.user.eh_administrador:
                raise PermissionDenied
            formulario = FormularioGestao(requisicao.POST) if acao == 'gerenciar' else FormularioIncidente(requisicao.POST, chamado=chamado)
            if not formulario.is_valid():
                raise ValidationError([f'{campo}: {erro}' for campo, erros in formulario.errors.items() for erro in erros])
            if acao == 'gerenciar':
                fluxo.gerenciar(requisicao.user, id, formulario.cleaned_data)
            else:
                fluxo.vincular(requisicao.user, id, formulario.cleaned_data['incidente'])
        else:
            from django.http import Http404
            raise Http404
    except ValidationError as erro:
        messages.error(requisicao, '; '.join(erro.messages))
    else:
        messages.success(requisicao, 'Atendimento atualizado.')
    return redirect('detalhe', id=id)


@login_required
@require_http_methods(['GET', 'POST'])
def notificacoes(requisicao):
    consulta = fluxo.notificacoes_visiveis(requisicao.user)
    if requisicao.method == 'POST':
        consulta.filter(lida_em__isnull=True).update(lida_em=timezone.now())
        return redirect('notificacoes')
    return render(requisicao, 'chamados/notificacoes.html', {
        'pagina': Paginator(consulta, 30).get_page(requisicao.GET.get('page'))})


@login_required
@require_http_methods(['GET'])
def contagem_notificacoes(requisicao):
    resposta = JsonResponse({'naoLidas': fluxo.notificacoes_visiveis(requisicao.user).filter(lida_em__isnull=True).count()})
    resposta['Cache-Control'] = 'private, no-store'
    return resposta
