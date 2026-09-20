"""ModelForms seguem o padrão LivroForm do ZIP, agora para o HelpDesk."""
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import Usuario, Chamado, MensagemChamado, Categoria
from . import fluxo


class ArquivosInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ArquivosField(forms.FileField):
    widget = ArquivosInput

    def clean(self, data, initial=None):
        if not data:
            return []
        arquivos = data if isinstance(data, (list, tuple)) else [data]
        arquivos = [super(ArquivosField, self).clean(a, initial) for a in arquivos]
        return fluxo.validar_arquivos(arquivos)

def validar_anexo(arquivo):
    if not arquivo:
        return arquivo
    if arquivo.size > 5 * 1024 * 1024:
        raise forms.ValidationError('O anexo deve ter no máximo 5 MB.')
    ext = Path(arquivo.name).suffix.lower()
    try:
        if ext == '.pdf':
            if not arquivo.read(5) == b'%PDF-':
                raise forms.ValidationError('O conteúdo não é um PDF válido.')
            arquivo.content_type = 'application/pdf'
        elif ext in ('.png', '.jpg', '.jpeg'):
            img = Image.open(arquivo)
            expected = 'PNG' if ext == '.png' else 'JPEG'
            if img.format != expected:
                raise forms.ValidationError('O conteúdo não corresponde à extensão da imagem.')
            img.verify()
            arquivo.content_type = 'image/png' if ext == '.png' else 'image/jpeg'
        else:
            raise forms.ValidationError('Envie apenas PNG, JPG ou PDF.')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise forms.ValidationError('Imagem inválida.')
    finally:
        arquivo.seek(0)
    return arquivo

class LoginForm(forms.Form):
    email = forms.EmailField(label='E-mail', max_length=180)
    password = forms.CharField(label='Senha', widget=forms.PasswordInput, max_length=256, strip=False)

class UsuarioForm(forms.ModelForm):
    password = forms.CharField(label='Senha', min_length=8, max_length=72,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), strip=False)
    name = forms.CharField(label='Nome', min_length=2, max_length=120)

    class Meta:
        model = Usuario
        fields = ['name', 'email', 'role']
        widgets = {'email': forms.EmailInput(attrs={'autocomplete': 'off'})}

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Já existe um usuário com este e-mail.')
        return email

    def clean(self):
        data = super().clean()
        if data.get('password'):
            user = Usuario(email=data.get('email', ''), name=data.get('name', ''))
            try:
                validate_password(data['password'], user)
            except forms.ValidationError as error:
                self.add_error('password', error)
        return data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data['password'])
        if commit:
            usuario.save()
        return usuario

class ChamadoForm(forms.ModelForm):
    assunto = forms.CharField(min_length=3, max_length=150)
    descricao = forms.CharField(label='Descrição', min_length=10, max_length=5000,
        widget=forms.Textarea(attrs={'rows': 6}))
    anexo = ArquivosField(required=False, label='Anexos',
        help_text='Até 5 arquivos PNG, JPG ou PDF: 5 MB por arquivo e 20 MB no total.',
        widget=ArquivosInput(attrs={'accept': '.png,.jpg,.jpeg,.pdf'}))
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.filter(ativa=True), required=False,
        empty_label='Outros / não sei identificar')

    class Meta:
        model = Chamado
        fields = ['assunto', 'descricao', 'categoria', 'urgencia']
        labels = {'urgencia': 'Urgência'}

    def clean_anexo(self):
        return self.cleaned_data.get('anexo', [])

class MensagemForm(forms.ModelForm):
    conteudo = forms.CharField(label='Sua mensagem', min_length=1, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Escreva uma atualização...'}))
    interna = forms.BooleanField(label='Nota interna (somente equipe)', required=False)
    anexo = ArquivosField(label='Anexos', required=False,
        help_text='Até 5 arquivos; 5 MB por arquivo e 20 MB no total.',
        widget=ArquivosInput(attrs={'accept': '.png,.jpg,.jpeg,.pdf'}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None and not usuario.is_admin:
            self.fields.pop('interna')
    class Meta:
        model = MensagemChamado
        fields = ['conteudo']

class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=[c for c in Chamado.Status.choices if c[0] != 'CLOSED'])
    solucao = forms.CharField(label='Solução (obrigatória ao resolver)', required=False, max_length=5000,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Ao resolver um incidente principal, esta solução será enviada aos chamados vinculados.')
    motivo = forms.CharField(label='Motivo (obrigatório ao cancelar ou reabrir)', required=False,
        max_length=2000, widget=forms.Textarea(attrs={'rows': 2}))


class GerenciarForm(forms.Form):
    responsavel = forms.ModelChoiceField(label='Responsável', queryset=Usuario.objects.none(),
        required=False, empty_label='Sem responsável')
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.filter(ativa=True))
    urgencia = forms.ChoiceField(label='Urgência', choices=Chamado.Urgencia.choices)
    prazo_resposta = forms.DateTimeField(label='Prazo da primeira resposta',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    prazo_resolucao = forms.DateTimeField(label='Prazo da resolução',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    motivo = forms.CharField(label='Justificativa da alteração', required=False, max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsavel'].queryset = fluxo.tecnicos()


class ReabrirForm(forms.Form):
    motivo = forms.CharField(label='O que ainda não funciona?', min_length=5, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}))


class IncidenteForm(forms.Form):
    incidente = forms.ModelChoiceField(queryset=Chamado.objects.none(), required=False,
        label='Incidente principal', empty_label='Sem vínculo')

    def __init__(self, *args, chamado, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['incidente'].queryset = Chamado.objects.filter(incidente__isnull=True).exclude(
            pk=chamado.pk).exclude(status__in=['RESOLVED', 'CLOSED', 'CANCELLED'])
