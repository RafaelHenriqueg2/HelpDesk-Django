from datetime import timedelta
from django.db import migrations


def preparar(apps, schema_editor):
    Categoria = apps.get_model('chamados', 'Categoria')
    Chamado = apps.get_model('chamados', 'Chamado')
    Evento = apps.get_model('chamados', 'EventoChamado')
    Historico = apps.get_model('chamados', 'HistoricoStatus')
    alias = schema_editor.connection.alias
    for nome in ['Acesso', 'Computador', 'Impressora', 'Internet', 'Sistemas', 'Outros']:
        Categoria.objects.using(alias).get_or_create(nome=nome)
    outros = Categoria.objects.using(alias).get(nome='Outros')
    prazos = {'LOW': (24, 72), 'MEDIUM': (8, 24), 'HIGH': (2, 8), 'CRITICAL': (.5, 4)}
    for chamado in Chamado.objects.using(alias).all().iterator():
        resposta, resolucao = prazos[chamado.urgencia]
        chamado.categoria = outros
        chamado.prazo_resposta = chamado.criado_em + timedelta(hours=resposta)
        chamado.prazo_resolucao = chamado.criado_em + timedelta(hours=resolucao)
        # Não inventar datas de resposta ou soluções para dados antigos.
        chamado.save(using=alias, update_fields=['categoria', 'prazo_resposta', 'prazo_resolucao'])
        Evento.objects.using(alias).create(chamado_id=chamado.pk, autor_id=chamado.usuario_id,
            campo='Abertura', novo='Chamado anterior à atualização', criado_em=chamado.criado_em)
    nomes = {'OPEN': 'Aberto', 'IN_PROGRESS': 'Em atendimento', 'RESOLVED': 'Resolvido'}
    for evento in Historico.objects.using(alias).all().iterator():
        Evento.objects.using(alias).create(chamado_id=evento.chamado_id, autor_id=evento.autor_id,
            campo='Status', anterior=nomes.get(evento.anterior, evento.anterior),
            novo=nomes.get(evento.novo, evento.novo), criado_em=evento.criado_em)


class Migration(migrations.Migration):
    dependencies = [('chamados', '0003_evolucao_atendimento')]
    operations = [migrations.RunPython(preparar, migrations.RunPython.noop)]
