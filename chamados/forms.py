"""Formulários do portal e da API: validam os dados antes de executar o atendimento."""
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import Usuario, Chamado, MensagemChamado, Categoria
from . import fluxo


class EntradaMultiplosArquivos(forms.ClearableFileInput):
    allow_multiple_selected = True


class CampoMultiplosArquivos(forms.FileField):
    widget = EntradaMultiplosArquivos

    def clean(self, data, initial=None):
        # O Django fornece os arquivos; cada um passa pela validação do campo.
        if not data:
            return []
        arquivos = data if isinstance(data, (list, tuple)) else [data]
        arquivos = [super(CampoMultiplosArquivos, self).clean(arquivo, initial) for arquivo in arquivos]
        return fluxo.validar_arquivos(arquivos)

def validar_anexo(arquivo):
    """Confere tamanho e conteúdo; a extensão sozinha não comprova o formato."""
    if not arquivo:
        return arquivo
    if arquivo.size > 5 * 1024 * 1024:
        raise forms.ValidationError('O anexo deve ter no máximo 5 MB.')
    extensao = Path(arquivo.name).suffix.lower()
    try:
        if extensao == '.pdf':
            if not arquivo.read(5) == b'%PDF-':
                raise forms.ValidationError('O conteúdo não é um PDF válido.')
            arquivo.content_type = 'application/pdf'
        elif extensao in ('.png', '.jpg', '.jpeg'):
            imagem = Image.open(arquivo)
            formato_esperado = 'PNG' if extensao == '.png' else 'JPEG'
            if imagem.format != formato_esperado:
                raise forms.ValidationError('O conteúdo não corresponde à extensão da imagem.')
            imagem.verify()
            arquivo.content_type = 'image/png' if extensao == '.png' else 'image/jpeg'
        else:
            raise forms.ValidationError('Envie apenas PNG, JPG ou PDF.')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise forms.ValidationError('Imagem inválida.')
    finally:
        # A leitura de validação não pode deixar o arquivo no fim antes de salvá-lo.
        arquivo.seek(0)
    return arquivo

class CamposContaCompativeis:
    """Aceita o contrato antigo da API e entrega dados internos em português."""

    def __init__(self, data=None, *args, **kwargs):
        # `data` é um argumento nomeado usado pelo próprio Django.
        dados = data.copy() if data is not None else None
        if dados is not None:
            for antigo, novo in {'name': 'nome', 'role': 'perfil', 'password': 'senha'}.items():
                if antigo in dados and novo not in dados:
                    dados[novo] = dados[antigo]
        super().__init__(dados, *args, **kwargs)


class FormularioEntrada(CamposContaCompativeis, forms.Form):
    email = forms.EmailField(label='E-mail', max_length=180)
    senha = forms.CharField(label='Senha', widget=forms.PasswordInput, max_length=256, strip=False)

class FormularioUsuario(CamposContaCompativeis, forms.ModelForm):
    senha = forms.CharField(label='Senha', min_length=8, max_length=72,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), strip=False)
    nome = forms.CharField(label='Nome', min_length=2, max_length=120)

    class Meta:
        model = Usuario
        fields = ['nome', 'email', 'perfil']
        widgets = {'email': forms.EmailInput(attrs={'autocomplete': 'off'})}

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Já existe um usuário com este e-mail.')
        return email

    def clean(self):
        dados = super().clean()
        if dados.get('senha'):
            usuario = Usuario(email=dados.get('email', ''), nome=dados.get('nome', ''))
            try:
                validate_password(dados['senha'], usuario)
            except forms.ValidationError as erro:
                self.add_error('senha', erro)
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data['senha'])
        if commit:
            usuario.save()
        return usuario

class FormularioChamado(forms.ModelForm):
    assunto = forms.CharField(min_length=3, max_length=150)
    descricao = forms.CharField(label='Descrição', min_length=10, max_length=5000,
        widget=forms.Textarea(attrs={'rows': 6}))
    anexo = CampoMultiplosArquivos(required=False, label='Anexos',
        help_text='Até 5 arquivos PNG, JPG ou PDF: 5 MB por arquivo e 20 MB no total.',
        widget=EntradaMultiplosArquivos(attrs={'accept': '.png,.jpg,.jpeg,.pdf'}))
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.filter(ativa=True), required=False,
        empty_label='Outros / não sei identificar')

    class Meta:
        model = Chamado
        fields = ['assunto', 'descricao', 'categoria', 'urgencia']
        labels = {'urgencia': 'Urgência'}

    def clean_anexo(self):
        return self.cleaned_data.get('anexo', [])

class FormularioMensagem(forms.ModelForm):
    conteudo = forms.CharField(label='Sua mensagem', min_length=1, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Escreva uma atualização...'}))
    interna = forms.BooleanField(label='Nota interna (somente equipe)', required=False)
    anexo = CampoMultiplosArquivos(label='Anexos', required=False,
        help_text='Até 5 arquivos; 5 MB por arquivo e 20 MB no total.',
        widget=EntradaMultiplosArquivos(attrs={'accept': '.png,.jpg,.jpeg,.pdf'}))

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None and not usuario.eh_administrador:
            self.fields.pop('interna')
    class Meta:
        model = MensagemChamado
        fields = ['conteudo']

class FormularioSituacao(forms.Form):
    status = forms.ChoiceField(choices=[opcao for opcao in Chamado.Situacao.choices if opcao[0] != 'CLOSED'])
    solucao = forms.CharField(label='Solução (obrigatória ao resolver)', required=False, max_length=5000,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Ao resolver um incidente principal, esta solução será enviada aos chamados vinculados.')
    motivo = forms.CharField(label='Motivo (obrigatório ao cancelar ou reabrir)', required=False,
        max_length=2000, widget=forms.Textarea(attrs={'rows': 2}))


class FormularioGestao(forms.Form):
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


class FormularioReabertura(forms.Form):
    motivo = forms.CharField(label='O que ainda não funciona?', min_length=5, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}))


class FormularioIncidente(forms.Form):
    incidente = forms.ModelChoiceField(queryset=Chamado.objects.none(), required=False,
        label='Incidente principal', empty_label='Sem vínculo')

    def __init__(self, *args, chamado, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['incidente'].queryset = Chamado.objects.filter(incidente__isnull=True).exclude(
            pk=chamado.pk).exclude(status__in=['RESOLVED', 'CLOSED', 'CANCELLED'])
