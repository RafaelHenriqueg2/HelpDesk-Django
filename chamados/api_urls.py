from django.urls import path
from . import api

urlpatterns = [
    path('status', api.HealthAPI.as_view()),
    path('auth/login', api.LoginAPI.as_view()),
    path('auth/me', api.MeAPI.as_view()),
    path('users', api.UsersAPI.as_view()),
    path('users/<uuid:id>', api.UserAPI.as_view()),
    path('categorias', api.CategoriaAPI.as_view()),
    path('notificacoes', api.NotificacoesAPI.as_view()),
    path('notificacoes/<int:id>/ler', api.LerNotificacaoAPI.as_view()),
    path('chamados', api.ChamadosAPI.as_view()),
    path('chamados/<uuid:id>', api.ChamadoAPI.as_view()),
    path('chamados/<uuid:id>/status', api.StatusAPI.as_view()),
    path('chamados/<uuid:id>/gestao', api.GestaoAPI.as_view()),
    path('chamados/<uuid:id>/confirmar', api.ConfirmarAPI.as_view()),
    path('chamados/<uuid:id>/reabrir', api.ReabrirAPI.as_view()),
    path('chamados/<uuid:id>/incidente', api.IncidenteAPI.as_view()),
    path('chamados/<uuid:id>/historico', api.HistoricoAPI.as_view()),
    path('chamados/<uuid:id>/mensagens', api.MensagemAPI.as_view()),
    path('chamados/<uuid:id>/anexos/<uuid:anexo_id>', api.AnexoAPI.as_view()),
]
