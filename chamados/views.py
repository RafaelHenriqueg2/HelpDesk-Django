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
from .forms import LoginForm, UsuarioForm, ChamadoForm, MensagemForm, StatusForm
from .models import Usuario, Chamado, RegistroLogin
from . import services
from . import fluxo
from .models import Categoria, Notificacao
from .forms import GerenciarForm, ReabrirForm, IncidenteForm

def admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped

def inicio(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect('dashboard' if request.user.is_admin else 'home')

@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return inicio(request)
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = services.entrar(request, **form.cleaned_data)
        if usuario:
            login(request, usuario)
            return inicio(request)
        form.add_error(None, 'E-mail ou senha inválidos.')
    return render(request, 'chamados/login.html', {'form': form})

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def home(request):
    return painel(request)

@admin_required
def dashboard(request):
    return painel(request)

def painel(request):
    chamados = services.consultar(request.user)
    contagem = dict(chamados.order_by().values('status').annotate(total=Count('numero')).values_list('status', 'total'))
    resumo = [{'status': code, 'label': label, 'total': contagem.get(code, 0)} for code, label in Chamado.Status.choices]
    busca = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    categoria = request.GET.get('categoria', '')
    urgencia = request.GET.get('urgencia', '')
    meus = request.GET.get('meus') == '1'
    fila = request.GET.get('fila', '')
    prazo = request.GET.get('prazo', '')
    if categoria.isdecimal() and len(categoria) < 10:
        chamados = chamados.filter(categoria_id=int(categoria))
    if urgencia in Chamado.Urgencia.values:
        chamados = chamados.filter(urgencia=urgencia)
    if request.user.is_admin and meus:
        chamados = chamados.filter(responsavel=request.user)
    if request.user.is_admin and fila == 'sem':
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
    pendentes = fluxo.notificacoes_visiveis(request.user).filter(
        chamado_id=OuterRef('pk'), lida_em__isnull=True)
    chamados = chamados.annotate(nao_lidas=Exists(pendentes))
    if request.GET.get('nao_lidas') == '1':
        chamados = chamados.filter(nao_lidas=True)
    if status in Chamado.Status.values:
        chamados = chamados.filter(status=status)
    if busca:
        filtro = Q(assunto__icontains=busca)
        numero = busca.upper().removeprefix('HD-')
        if numero.isdecimal() and len(numero) <= 18:
            filtro |= Q(numero=int(numero))
        if request.user.is_admin:
            filtro |= Q(usuario__name__icontains=busca) | Q(usuario__email__icontains=busca)
        chamados = chamados.filter(filtro)
    return render(request, 'chamados/lista.html', {'page': Paginator(chamados, 20).get_page(request.GET.get('page')),
        'resumo': resumo, 'total': sum(contagem.values()), 'busca': busca, 'status': status,
        'categorias': Categoria.objects.filter(ativa=True), 'categoria': categoria,
        'urgencias': Chamado.Urgencia.choices, 'urgencia': urgencia, 'meus': meus,
        'fila': fila, 'prazo': prazo, 'filtros': request.GET})

@login_required
@require_http_methods(['GET', 'POST'])
def novo_chamado(request):
    form = ChamadoForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        chamado = services.criar_chamado(request.user, form.cleaned_data)
        messages.success(request, f'Chamado enviado com sucesso. Protocolo {chamado.protocolo}.')
        return redirect('detalhe', id=chamado.id)
    return render(request, 'chamados/form.html', {'form': form, 'titulo': 'Abrir novo chamado',
        'subtitulo': 'Conte o que aconteceu para nossa equipe ajudar você.', 'botao': 'Enviar chamado'})

@login_required
@require_http_methods(['GET', 'POST'])
def detalhe(request, id):
    chamado = services.buscar(request.user, id)
    form = MensagemForm(request.POST or None, request.FILES or None, usuario=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            services.enviar_mensagem(request.user, id, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Mensagem enviada.')
            return redirect('detalhe', id=id)
    conversa = Paginator(fluxo.mensagens_visiveis(chamado, request.user).order_by(
        '-criado_em', '-id'), 30).get_page(request.GET.get('mensagens'))
    historico = Paginator(fluxo.eventos_visiveis(chamado, request.user), 20).get_page(request.GET.get('historico'))
    # Mark only notifications that existed before this response was assembled.
    corte = timezone.now()
    fluxo.notificacoes_visiveis(request.user).filter(chamado=chamado,
        lida_em__isnull=True, criado_em__lte=corte).update(lida_em=corte)
    return render(request, 'chamados/detalhe.html', {'chamado': chamado, 'form': form,
        'status_form': StatusForm(initial={'status': chamado.status}, auto_id='status_%s'),
        'gestao_form': GerenciarForm(initial={f: getattr(chamado, f) for f in
            ['responsavel', 'categoria', 'urgencia', 'prazo_resposta', 'prazo_resolucao']}, auto_id='gestao_%s'),
        'reabrir_form': ReabrirForm(auto_id='reabrir_%s'), 'incidente_form': IncidenteForm(chamado=chamado,
            initial={'incidente': chamado.incidente_id}, auto_id='incidente_%s'),
        'conversa': conversa, 'historico': historico,
        'anexos': fluxo.anexos_visiveis(chamado, request.user).filter(mensagem__isnull=True),
        'duplicados': chamado.duplicados.all() if request.user.is_admin else [],
        'pode_confirmar': chamado.usuario_id == request.user.pk and chamado.status == 'RESOLVED',
        'pode_reabrir': chamado.status in ('RESOLVED', 'CLOSED')})

@admin_required
@require_POST
def status_view(request, id):
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            services.alterar_status(request.user, id, **form.cleaned_data)
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(request, 'Status atualizado.')
    else:
        messages.error(request, 'Status inválido.')
    return redirect('detalhe', id=id)

@login_required
def anexo(request, id, anexo_id):
    return services.baixar_anexo(request.user, id, anexo_id)

@admin_required
@require_http_methods(['GET', 'POST'])
def usuarios(request):
    form = UsuarioForm(request.POST or None, initial={'role': 'USER'})
    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error('email', 'Já existe um usuário com este e-mail.')
        else:
            messages.success(request, 'Usuário cadastrado com sucesso.')
            return redirect('usuarios')
    busca = request.GET.get('q', '').strip()
    lista = services.usuarios_disponiveis()
    if busca:
        lista = lista.filter(Q(name__icontains=busca) | Q(email__icontains=busca))
    page = Paginator(lista, 20).get_page(request.GET.get('page'))
    for usuario in page:
        usuario.pode_excluir = services.pode_excluir_usuario(request.user, usuario)
    return render(request, 'chamados/usuarios.html', {'form': form, 'busca': busca, 'page': page})

@admin_required
def usuario_detalhe(request, id):
    usuario = get_object_or_404(services.usuarios_disponiveis(), pk=id)
    return render(request, 'chamados/usuario.html', {'usuario': usuario,
        'pode_excluir': services.pode_excluir_usuario(request.user, usuario)})


@admin_required
@require_http_methods(['GET', 'POST'])
def usuario_excluir(request, id):
    usuario = get_object_or_404(services.usuarios_disponiveis(), pk=id)
    if not services.pode_excluir_usuario(request.user, usuario):
        raise PermissionDenied('Não é permitido excluir esta conta.')
    if request.method == 'POST':
        if request.POST.get('confirmar') != 'sim':
            messages.error(request, 'Confirme a exclusão para continuar.')
        else:
            try:
                services.excluir_usuario(request.user, id)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(request, f'Conta de {usuario.name} excluída. O histórico foi preservado.')
                return redirect('usuarios')
    return render(request, 'chamados/usuario_excluir.html', {'usuario': usuario})

@admin_required
def auditoria(request):
    return render(request, 'chamados/auditoria.html', {
        'page': Paginator(RegistroLogin.objects.all(), 30).get_page(request.GET.get('page'))})


@login_required
@require_POST
def acao_chamado(request, id, acao):
    chamado = services.buscar(request.user, id)
    try:
        if acao == 'confirmar':
            fluxo.confirmar(request.user, id)
        elif acao == 'reabrir':
            form = ReabrirForm(request.POST)
            if not form.is_valid():
                raise ValidationError('Explique o motivo da reabertura (5 a 2000 caracteres).')
            fluxo.reabrir(request.user, id, form.cleaned_data['motivo'])
        elif acao in ('gerenciar', 'vincular'):
            if not request.user.is_admin:
                raise PermissionDenied
            form = GerenciarForm(request.POST) if acao == 'gerenciar' else IncidenteForm(request.POST, chamado=chamado)
            if not form.is_valid():
                raise ValidationError([f'{campo}: {erro}' for campo, erros in form.errors.items() for erro in erros])
            if acao == 'gerenciar':
                fluxo.gerenciar(request.user, id, form.cleaned_data)
            else:
                fluxo.vincular(request.user, id, form.cleaned_data['incidente'])
        else:
            from django.http import Http404
            raise Http404
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(request, 'Atendimento atualizado.')
    return redirect('detalhe', id=id)


@login_required
@require_http_methods(['GET', 'POST'])
def notificacoes(request):
    qs = fluxo.notificacoes_visiveis(request.user)
    if request.method == 'POST':
        qs.filter(lida_em__isnull=True).update(lida_em=timezone.now())
        return redirect('notificacoes')
    return render(request, 'chamados/notificacoes.html', {
        'page': Paginator(qs, 30).get_page(request.GET.get('page'))})


@login_required
@require_http_methods(['GET'])
def contagem_notificacoes(request):
    response = JsonResponse({'naoLidas': fluxo.notificacoes_visiveis(request.user).filter(lida_em__isnull=True).count()})
    response['Cache-Control'] = 'private, no-store'
    return response
