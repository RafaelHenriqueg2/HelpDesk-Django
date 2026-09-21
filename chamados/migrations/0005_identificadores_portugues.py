"""Renomeia campos existentes sem recriar usuários ou perder seus vínculos."""
from django.db import migrations, models
import chamados.models


class Migration(migrations.Migration):
    dependencies = [('chamados', '0004_preparar_categorias_prazos')]

    operations = [
        # A restrição deve acompanhar o nome novo, inclusive no SQLite.
        migrations.RemoveConstraint('usuario', 'usuario_excluido_inativo'),
        migrations.RenameField('usuario', 'name', 'nome'),
        migrations.RenameField('usuario', 'role', 'perfil'),
        migrations.RenameField('usuario', 'created_at', 'criado_em'),
        migrations.RenameField('usuario', 'updated_at', 'atualizado_em'),
        migrations.RenameField('usuario', 'deleted_at', 'excluido_em'),
        migrations.RenameField('usuario', 'deleted_by', 'excluido_por'),
        migrations.AlterModelOptions('usuario', {'ordering': ['-criado_em']}),
        migrations.AlterModelManagers('usuario', [('objects', chamados.models.GerenciadorUsuarios())]),
        migrations.AddConstraint('usuario', models.CheckConstraint(
            condition=models.Q(excluido_em__isnull=True) | models.Q(is_active=False),
            name='usuario_excluido_inativo')),
    ]
