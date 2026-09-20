from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('login', views.login_view, name='login'),
    path('logout', views.logout_view, name='logout'),
    path('home', views.home, name='home'),
    path('tickets/new', views.novo_chamado, name='novo'),
    path('tickets/<uuid:id>', views.detalhe, name='detalhe'),
    path('tickets/<uuid:id>/status', views.status_view, name='status'),
    path('tickets/<uuid:id>/acoes/<str:acao>', views.acao_chamado, name='acao_chamado'),
    path('notificacoes', views.notificacoes, name='notificacoes'),
    path('notificacoes/contagem', views.contagem_notificacoes, name='contagem_notificacoes'),
    path('tickets/<uuid:id>/anexos/<uuid:anexo_id>', views.anexo, name='anexo'),
    path('admin', views.dashboard, name='dashboard'),
    path('admin/users', views.usuarios, name='usuarios'),
    path('admin/users/<uuid:id>', views.usuario_detalhe, name='usuario'),
    path('admin/users/<uuid:id>/excluir', views.usuario_excluir, name='usuario_excluir'),
    path('admin/logins', views.auditoria, name='auditoria'),
]
