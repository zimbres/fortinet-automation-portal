import pytest
from django.core.exceptions import PermissionDenied
from apps.accounts.models import GroupGrant
from apps.firewalls.models import Firewall,VDOM,FirewallGroup,FirewallGroupMember
from apps.inventory.models import InventoryScan
from tests.test_catalog import manager
from tests.group_helpers import group_for

pytestmark=pytest.mark.django_db


@pytest.fixture
def usage_group(manager,scope):
    group=FirewallGroup.objects.create(name='Usage targets')
    second=VDOM.objects.create(firewall=Firewall.objects.create(name='Second usage device',hostname='192.0.2.2'),name='root')
    for vd in (scope[2],second): FirewallGroupMember.objects.create(group=group,firewall=vd.firewall,vdom=vd)
    GroupGrant.objects.create(user=manager,firewall_group=group,capability='view')
    return group,second


def test_group_classification_tracks_policy_and_nested_group_usage():
    from apps.inventory.usage import classify_usage
    findings=classify_usage([{'name':'host'}],[{'name':'outer','member':[{'name':'inner'}]},{'name':'inner','member':[{'name':'outer'},{'name':'host'}]},{'name':'unused','member':[]}],[{'srcaddr':[{'name':'outer'}],'dstaddr':[]}],complete=True,include_groups=True)
    assert findings=={'host':'used','inner':'used','outer':'used','unused':'potentially_unused'}
    assert classify_usage([], [{'name':'group','member':[]}],[{'srcaddr':[{'name':'all'}],'dstaddr':[]}],complete=True,include_groups=True)=={'group':'potentially_unused'}


def test_group_scan_filters_both_types_and_continues_after_failure(usage_group,manager,scope,monkeypatch):
    from apps.inventory import services
    from apps.inventory.catalog import save_address,save_address_group
    from apps.fortinet.exceptions import FortinetError
    from apps.audit.models import AuditEvent
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    save_address_group(actor=manager,name='local_group',member_ids=[])
    calls=[]
    class Remote:
        def __init__(self,fw,vd): self.vd=vd; calls.append(vd.pk)
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def list_addresses(self):
            if self.vd.pk==scope[2].pk: raise FortinetError('not reachable')
            return [{'name':'local_host'},{'name':'remote_only'}]
        def list_groups(self): return [{'name':'local_group','member':[{'name':'local_host'}]},{'name':'remote_group','member':[{'name':'local_group'}]}]
        def list_policies(self): return [{'srcaddr':[{'name':'remote_group'}],'dstaddr':[]}]
    monkeypatch.setattr(services,'FortinetClient',Remote)
    for _ in range(2): results=services.scan_group_usage(actor=manager,firewall_group_id=usage_group[0].pk)
    assert len(results)==2 and len(calls)==4 and InventoryScan.objects.count()==2
    failed=InventoryScan.objects.get(vdom=scope[2]); good=InventoryScan.objects.get(vdom=usage_group[1])
    assert not failed.complete and failed.findings=={} and failed.group_findings=={}
    assert good.findings=={'local_host':'used'} and good.group_findings=={'local_group':'used'}
    assert AuditEvent.objects.filter(event_type='inventory.scanned').count()==4


def test_group_scan_requires_exact_group_grant(manager,scope):
    from apps.inventory.services import scan_group_usage
    other=FirewallGroup.objects.create(name='Not granted')
    FirewallGroupMember.objects.create(group=other,firewall=scope[2].firewall,vdom=scope[2])
    with pytest.raises(PermissionDenied): scan_group_usage(actor=manager,firewall_group_id=other.pk)


def test_usage_page_selects_group_and_shows_separate_resource_types(client,manager,scope,usage_group):
    from apps.inventory.catalog import save_address,save_address_group
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    save_address_group(actor=manager,name='local_group',member_ids=[])
    InventoryScan.objects.create(vdom=usage_group[1],complete=True,findings={'local_host':'used'},group_findings={'local_group':'potentially_unused','nonlocal_group':'used'})
    client.force_login(manager)
    page=client.get('/usage/',{'firewall_group':usage_group[0].pk})
    assert page.status_code==200 and page.context['selected_group'].pk==usage_group[0].pk
    assert b'Scan group usage' in page.content and b'local_group' in page.content and b'nonlocal_group' not in page.content
    assert b'Address objects' in page.content and b'Address groups' in page.content
    page=client.get('/usage/',{'firewall_group':group_for(scope[2]).pk})
    assert b'local_group' not in page.content


def test_group_scan_post_keeps_selected_group(client,manager,scope,monkeypatch):
    from apps.inventory import services
    calls=[]
    monkeypatch.setattr(services,'scan_group_usage',lambda **kw:calls.append(kw) or [])
    client.force_login(manager)
    group=group_for(scope[2])
    response=client.post('/usage/',{'firewall_group':group.pk})
    assert response.status_code==302 and response.url.endswith(f'?firewall_group={group.pk}')
    assert calls[0]['firewall_group_id']==group.pk

def test_group_view_action_does_not_start_scan(client,manager,scope,monkeypatch):
    from apps.inventory import services
    def forbidden(**kwargs): raise AssertionError('View results must not contact firewalls')
    monkeypatch.setattr(services,'scan_group_usage',forbidden)
    client.force_login(manager)
    group=group_for(scope[2])
    assert client.post('/usage/',{'firewall_group':group.pk,'action':'view'}).status_code==302


def test_group_scan_empty_and_revoked_membership_are_guarded(manager,usage_group,monkeypatch):
    from apps.inventory import services
    from django.core.exceptions import ValidationError
    empty=FirewallGroup.objects.create(name='Empty usage group')
    GroupGrant.objects.create(user=manager,firewall_group=empty,capability='view')
    with pytest.raises(ValidationError): services.scan_group_usage(actor=manager,firewall_group_id=empty.pk)
    called=[]
    def first_scan(**kwargs):
        called.append(kwargs['vdom'].pk)
        GroupGrant.objects.filter(user=manager,firewall_group=usage_group[0]).delete()
        return InventoryScan(vdom=kwargs['vdom'],complete=True)
    monkeypatch.setattr(services,'scan_usage',first_scan)
    with pytest.raises(PermissionDenied): services.scan_group_usage(actor=manager,firewall_group_id=usage_group[0].pk)
    assert len(called)==1


def test_old_scan_does_not_claim_address_groups_were_assessed(client,manager,scope):
    InventoryScan.objects.create(vdom=scope[2],complete=True,findings={})
    client.force_login(manager)
    assert b'not assessed in this older result' in client.get('/usage/').content

def test_usage_intersection_matches_resource_type(manager,scope,monkeypatch):
    from apps.inventory import services
    from apps.inventory.catalog import save_address,save_address_group
    save_address(actor=manager,name='local_host',kind='subnet',value='192.0.2.1')
    save_address_group(actor=manager,name='local_group',member_ids=[])
    class Remote:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def list_addresses(self): return [{'name':'local_group'}]
        def list_groups(self): return [{'name':'local_host','member':[]}]
        def list_policies(self): return []
    monkeypatch.setattr(services,'FortinetClient',lambda *args:Remote())
    scan=services.scan_usage(actor=manager,vdom=scope[2])
    assert scan.findings=={} and scan.group_findings=={}
