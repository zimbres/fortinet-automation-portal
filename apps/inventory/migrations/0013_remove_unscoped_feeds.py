import django.db.models.deletion
from django.db import migrations, models


def remove_unscoped_feeds(apps, schema_editor):
    # Delete only unsupported publications and their account links. Accounts,
    # catalog entries, approved scoped feeds and audit/request history remain.
    apps.get_model('inventory', 'ThreatFeed').objects.using(schema_editor.connection.alias).filter(
        scope__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('inventory', '0012_threatfeedidentity')]

    operations = [
        migrations.RunPython(remove_unscoped_feeds, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='threatfeed', name='scope',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='feeds', to='inventory.threatfeedscope'),
        ),
    ]
