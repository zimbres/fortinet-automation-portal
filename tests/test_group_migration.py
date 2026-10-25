import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_group_migration_discards_old_access_and_repairs_cancelled_execution():
    executor=MigrationExecutor(connection)
    latest=executor.loader.graph.leaf_nodes()
    before=[('accounts','0003_cataloggrant'),('changes','0002_installationrequest_installationtarget_and_more'),('firewalls','0004_alter_firewall_allowed_namespace'),('inventory','0004_inventoryscan_unique_current_usage_scan')]
    try:
        executor.migrate(before)
        apps=executor.loader.project_state(before).apps
        User=apps.get_model('accounts','User')
        user=User.objects.create(username='previous_access')
        admin=User.objects.create(username='initial_admin',is_superuser=True,is_active=True)
        fw=apps.get_model('firewalls','Firewall').objects.create(name='Ungrouped',hostname='192.0.2.1')
        vd=apps.get_model('firewalls','VDOM').objects.create(firewall=fw,name='root')
        apps.get_model('accounts','ScopeGrant').objects.create(user=user,vdom=vd,capability='submit')
        item=apps.get_model('changes','InstallationRequest').objects.create(requester=user,snapshot={'target_kind':'firewall'},payload_digest='a'*64,idempotency_key='old',approval_status='CANCELLED')
        target=apps.get_model('changes','InstallationTarget').objects.create(request=item,vdom=vd,destination={})
        executor=MigrationExecutor(connection); executor.migrate(latest)
        current=executor.loader.project_state(latest).apps
        Grant=current.get_model('accounts','GroupGrant')
        assert not Grant.objects.filter(user_id=user.pk).exists()
        assert Grant.objects.filter(user_id=admin.pk).count()==4
        assert current.get_model('firewalls','FirewallGroupMember').objects.filter(firewall_id=fw.pk).count()==1
        assert current.get_model('changes','InstallationRequest').objects.get(pk=item.pk).execution_status=='CANCELLED'
        assert current.get_model('changes','InstallationTarget').objects.get(pk=target.pk).execution_status=='CANCELLED'
    finally:
        MigrationExecutor(connection).migrate(latest)
