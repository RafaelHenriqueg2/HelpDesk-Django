"""Move anexos do armazenamento de arquivos para Base64 no banco de dados."""
import base64
from pathlib import Path
import uuid
from django.core.files.base import ContentFile
from django.db import migrations, models


def converter_para_base64(aplicacoes, editor_schema):
    Anexo = aplicacoes.get_model('chamados', 'Anexo')
    for anexo in Anexo.objects.exclude(arquivo='').iterator():
        with anexo.arquivo.open('rb') as arquivo:
            anexo.conteudo_base64 = base64.b64encode(arquivo.read()).decode('ascii')
        anexo.save(update_fields=['conteudo_base64'])


def restaurar_arquivos(aplicacoes, editor_schema):
    Anexo = aplicacoes.get_model('chamados', 'Anexo')
    for anexo in Anexo.objects.exclude(conteudo_base64='').iterator():
        conteudo = base64.b64decode(anexo.conteudo_base64)
        extensao = Path(anexo.nome).suffix.lower()
        nome = f'anexos/{uuid.uuid4()}{extensao}'
        anexo.arquivo.save(nome, ContentFile(conteudo), save=False)
        anexo.save(update_fields=['arquivo'])


class Migration(migrations.Migration):
    dependencies = [('chamados', '0005_identificadores_portugues')]

    operations = [
        migrations.AddField(
            model_name='anexo',
            name='conteudo_base64',
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.RunPython(converter_para_base64, restaurar_arquivos),
        migrations.RemoveField(model_name='anexo', name='arquivo'),
        migrations.AlterField(
            model_name='anexo',
            name='conteudo_base64',
            field=models.TextField(editable=False),
        ),
    ]
