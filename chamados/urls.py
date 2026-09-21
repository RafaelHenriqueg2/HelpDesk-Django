from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('login', views.entrar, name='login'),
    path('logout', views.sair, name='logout'),
    path('home', views.pagina_usuario, name='home'),
    path('tickets/new', views.novo_chamado, name='novo'),
    path('tickets/<uuid:id>', views.detalhe, name='detalhe'),
    path('tickets/<uuid:id>/status', views.alterar_situacao, name='status'),
    path('tickets/<uuid:id>/acoes/<str:acao>', views.acao_chamado, name='acao_chamado'),
    path('notificacoes', views.notificacoes, name='notificacoes'),
    path('notificacoes/contagem', views.contagem_notificacoes, name='contagem_notificacoes'),
    path('tickets/<uuid:id>/anexos/<uuid:anexo_id>', views.anexo, name='anexo'),
    path('admin', views.painel_administrativo, name='dashboard'),
    path('admin/users', views.usuarios, name='usuarios'),
    path('admin/users/<uuid:id>', views.usuario_detalhe, name='usuario'),
    path('admin/users/<uuid:id>/excluir', views.usuario_excluir, name='usuario_excluir'),
    path('admin/logins', views.auditoria, name='auditoria'),
]
