"""Configura a administração técnica e impede alterações diretas na auditoria."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Usuario, Chamado, Anexo, MensagemChamado, RegistroLogin, HistoricoStatus
from .models import Categoria, EventoChamado, Notificacao

class FormularioCriacaoAdministrativa(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('email', 'nome', 'perfil')

class FormularioEdicaoAdministrativa(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = '__all__'

@admin.register(Usuario)
class AdministracaoUsuarios(UserAdmin):
    add_form = FormularioCriacaoAdministrativa
    form = FormularioEdicaoAdministrativa
    model = Usuario
    list_display = ('email', 'nome', 'perfil', 'is_active', 'excluido_em')
    ordering = ('email',)
    search_fields = ('email', 'nome')
    list_filter = ('perfil', 'is_active')
    fieldsets = ((None, {'fields': ('email', 'password', 'nome', 'perfil', 'is_active')}),
        ('Permissões', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}))
    add_fieldsets = ((None, {'fields': ('email', 'nome', 'perfil', 'password1', 'password2')}),)
    readonly_fields = ('excluido_em', 'excluido_por')
    fieldsets = fieldsets + (('Exclusão da conta', {'fields': readonly_fields}),)

    def has_delete_permission(self, requisicao, obj=None):
        # A exclusão passa pelo serviço do portal para preservar o histórico.
        return False

    def has_change_permission(self, requisicao, obj=None):
        if obj is not None and obj.excluido_em is not None:
            return False
        return super().has_change_permission(requisicao, obj)

class AdministracaoSomenteLeitura(admin.ModelAdmin):
    def has_add_permission(self, requisicao):
        return False
    def has_change_permission(self, requisicao, obj=None):
        return False
    def has_delete_permission(self, requisicao, obj=None):
        return False

@admin.register(RegistroLogin)
class AdministracaoRegistrosEntrada(AdministracaoSomenteLeitura):
    list_display = ('email_informado', 'sucesso', 'motivo_falha', 'criado_em')
    list_filter = ('sucesso',)

@admin.register(Chamado)
class AdministracaoChamados(AdministracaoSomenteLeitura):
    list_display = ('protocolo', 'assunto', 'status', 'urgencia', 'usuario')
    list_filter = ('status', 'urgencia')
    search_fields = ('assunto', 'usuario__email')

admin.site.register(MensagemChamado, AdministracaoSomenteLeitura)
admin.site.register(HistoricoStatus, AdministracaoSomenteLeitura)
admin.site.register(EventoChamado, AdministracaoSomenteLeitura)
admin.site.register(Notificacao, AdministracaoSomenteLeitura)


@admin.register(Categoria)
class AdministracaoCategorias(admin.ModelAdmin):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)
# Anexos não são expostos como links públicos no Django Admin.
admin.site.site_header = 'HelpDesk — Administração técnica'
