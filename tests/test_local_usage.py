import pytest
from tests.test_catalog import manager
from apps.inventory.models import InventoryScan

pytestmark=pytest.mark.django_db


def test_usage_intersects_local_catalog_after_full_reference_analysis(manager,scope,monkeypatch):
    from apps.inventory.catalog import save_address
    from apps.inventory.services import scan_usage
    from apps.inventory import services
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    save_address(actor=manager,name='local_only',kind='subnet',value='192.0.2.2')
    class Remote:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def list_addresses(self): return [{'name':'local_host'},{'name':'firewall_only'}]
        def list_groups(self): return [{'name':'external_group','member':[{'name':'local_host'}]}]
        def list_policies(self): return [{'srcaddr':[{'name':'external_group'}],'dstaddr':[]}]
    monkeypatch.setattr(services,'FortinetClient',lambda *args:Remote())
    scan=scan_usage(actor=manager,vdom=scope[2])
    assert scan.findings == {'local_host':'used'}


def test_usage_page_shows_latest_per_scope_and_current_local_names(client,manager,scope):
    from apps.inventory.catalog import save_address
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    latest=InventoryScan.objects.create(vdom=scope[2],complete=True,findings={'local_host':'used','firewall_only':'used'})
    client.force_login(manager)
    response=client.get('/usage/')
    assert [x.pk for x in response.context['scans']] == [latest.pk]
    assert b'local_host' in response.content
    assert b'old_result' not in response.content and b'firewall_only' not in response.content


def test_usage_does_not_reveal_local_catalog_without_access(client,scope):
    client.force_login(scope[0])
    assert client.get('/usage/').status_code == 403


def test_rescan_replaces_previous_result_and_audits_each_scan(manager,scope,monkeypatch):
    from apps.inventory.catalog import save_address
    from apps.inventory import services
    from apps.audit.models import AuditEvent
    from apps.fortinet.exceptions import FortinetError
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    class Remote:
        fail=False
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def list_addresses(self):
            if self.fail: raise FortinetError('scan failed')
            return [{'name':'local_host'}]
        def list_groups(self): return []
        def list_policies(self): return []
    remote=Remote()
    monkeypatch.setattr(services,'FortinetClient',lambda *args:remote)
    first=services.scan_usage(actor=manager,vdom=scope[2])
    remote.fail=True
    second=services.scan_usage(actor=manager,vdom=scope[2])
    assert first.pk==second.pk and InventoryScan.objects.filter(vdom=scope[2]).count()==1
    assert not second.complete and second.findings=={}
    assert AuditEvent.objects.filter(event_type='inventory.scanned').count()==2


def test_latest_usage_service_excludes_foreign_scopes(manager):
    from apps.firewalls.models import Firewall, VDOM
    from apps.inventory.services import latest_usage_scans
    foreign=VDOM.objects.create(firewall=Firewall.objects.create(name='Hidden',hostname='192.0.2.6'),name='root')
    InventoryScan.objects.create(vdom=foreign,findings={})
    assert latest_usage_scans(actor=manager,scopes=VDOM.objects.all())==[]
