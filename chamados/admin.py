from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Usuario, Chamado, Anexo, MensagemChamado, RegistroLogin, HistoricoStatus
from .models import Categoria, EventoChamado, Notificacao

class CriarUsuarioAdmin(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('email', 'name', 'role')

class EditarUsuarioAdmin(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = '__all__'

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = CriarUsuarioAdmin
    form = EditarUsuarioAdmin
    model = Usuario
    list_display = ('email', 'name', 'role', 'is_active', 'deleted_at')
    ordering = ('email',)
    search_fields = ('email', 'name')
    list_filter = ('role', 'is_active')
    fieldsets = ((None, {'fields': ('email', 'password', 'name', 'role', 'is_active')}),
        ('Permissões', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}))
    add_fieldsets = ((None, {'fields': ('email', 'name', 'role', 'password1', 'password2')}),)
    readonly_fields = ('deleted_at', 'deleted_by')
    fieldsets = fieldsets + (('Exclusão da conta', {'fields': readonly_fields}),)

    def has_delete_permission(self, request, obj=None):
        # Account removal belongs to the portal service, preserving history.
        return False

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.deleted_at is not None:
            return False
        return super().has_change_permission(request, obj)

class SomenteLeitura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(RegistroLogin)
class RegistroLoginAdmin(SomenteLeitura):
    list_display = ('email_informado', 'sucesso', 'motivo_falha', 'criado_em')
    list_filter = ('sucesso',)

@admin.register(Chamado)
class ChamadoAdmin(SomenteLeitura):
    list_display = ('protocolo', 'assunto', 'status', 'urgencia', 'usuario')
    list_filter = ('status', 'urgencia')
    search_fields = ('assunto', 'usuario__email')

admin.site.register(MensagemChamado, SomenteLeitura)
admin.site.register(HistoricoStatus, SomenteLeitura)
admin.site.register(EventoChamado, SomenteLeitura)
admin.site.register(Notificacao, SomenteLeitura)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)
# Anexos não são expostos como links públicos no Django Admin.
admin.site.site_header = 'HelpDesk — Administração técnica'
