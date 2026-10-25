import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_usage_migration_keeps_only_latest_result():
    from apps.firewalls.models import Firewall, VDOM
    executor=MigrationExecutor(connection)
    latest=executor.loader.graph.leaf_nodes()
    old=[('inventory','0003_catalogimport')]
    fw=Firewall.objects.create(name='Migration test',hostname='192.0.2.5')
    vdom=VDOM.objects.create(firewall=fw,name='root')
    survivor=None
    try:
        executor.migrate(old)
        Scan=executor.loader.project_state(old).apps.get_model('inventory','InventoryScan')
        first=Scan.objects.create(vdom_id=vdom.pk,findings={'older':'used'})
        last=Scan.objects.create(vdom_id=vdom.pk,findings={'latest':'used'})
        Scan.objects.filter(pk__in=[first.pk,last.pk]).update(created_at=timezone.now())
        survivor=last.pk
        executor=MigrationExecutor(connection)
        executor.migrate(latest)
        Scan=executor.loader.project_state(latest).apps.get_model('inventory','InventoryScan')
        assert list(Scan.objects.filter(vdom_id=vdom.pk).values_list('pk',flat=True))==[survivor]
        assert Scan.objects.get(pk=survivor).findings=={'latest':'used'}
    finally:
        # Keep the test DB usable even when the pre-fix migration rejects duplicates.
        with connection.cursor() as cursor:
            if survivor: cursor.execute('DELETE FROM inventory_inventoryscan WHERE vdom_id=%s AND id<>%s',[vdom.pk,survivor])
        MigrationExecutor(connection).migrate(latest)
