import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_upgrade_preserves_legacy_data_and_empty_catalog():
    old = [('accounts','0002_scopegrant'), ('firewalls','0001_initial'), ('changes','0001_initial'), ('inventory','0001_initial'), ('audit','0001_initial')]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model('accounts','User').objects.create(username='legacy')
        fw = apps.get_model('firewalls','Firewall').objects.create(name='Legacy',hostname='192.0.2.1',encrypted_token='preserved-ciphertext')
        vd = apps.get_model('firewalls','VDOM').objects.create(firewall=fw,name='root')
        apps.get_model('accounts','ScopeGrant').objects.create(user=user,vdom=vd,capability='submit')
        item = apps.get_model('changes','ChangeRequest').objects.create(requester=user,vdom=vd,operation='create_address',payload={'name':'legacy'},payload_digest='a'*64,idempotency_key='legacy')
        apps.get_model('changes','ObjectReference').objects.create(vdom=vd,name='legacy',originating_request=item)
        apps.get_model('audit','AuditEvent').objects.create(actor=user,event_type='legacy.event',metadata={})
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        assert current.get_model('changes','ChangeRequest').objects.get(pk=item.pk).payload_digest == 'a'*64
        assert current.get_model('firewalls','Firewall').objects.get(pk=fw.pk).encrypted_token == 'preserved-ciphertext'
        assert current.get_model('accounts','GroupGrant').objects.filter(user_id=user.pk).count() == 0
        assert current.get_model('changes','ObjectReference').objects.filter(originating_request_id=item.pk).count() == 1
        assert current.get_model('audit','AuditEvent').objects.filter(event_type='legacy.event').exists()
        assert current.get_model('inventory','CatalogEntry').objects.count() == 0
        assert current.get_model('accounts','CatalogGrant').objects.count() == 0
    finally:
        MigrationExecutor(connection).migrate(latest)
