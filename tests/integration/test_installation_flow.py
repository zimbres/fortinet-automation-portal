from tests.group_helpers import group_for
import os
import httpx
import pytest
from tests.test_catalog import manager
from tests.test_installations import installation
from tests.test_firewall_groups import admin
from tests.integration.test_portal_flow import SimulationTransport

pytestmark = [pytest.mark.django_db, pytest.mark.skipif(not os.environ.get('FORTINET_SIMULATION_URL'), reason='Start local Postman simulation.')]


@pytest.fixture
def installation_sim(monkeypatch):
    from apps.changes import installation_executor as executor, installation_reconciliation as reconciliation
    from apps.fortinet.client import FortinetClient
    base = os.environ['FORTINET_SIMULATION_URL']
    class DestinationTransport(SimulationTransport):
        def handle_request(self, request):
            request.headers['x-test-device'] = request.url.host
            return super().handle_request(request)
    factory = lambda fw,vd:FortinetClient(fw,vd,transport=DestinationTransport(base))
    monkeypatch.setattr(executor,'FortinetClient',factory)
    monkeypatch.setattr(reconciliation,'FortinetClient',factory)
    monkeypatch.setattr(executor,'require_write_capability',lambda *args:None)
    return base


@pytest.mark.parametrize('mode,expected', [('success','SUCCEEDED'),('partial_second','PARTIALLY_SUCCEEDED'),('uncertain','RECONCILIATION_REQUIRED'),('read_failure','RECONCILIATION_REQUIRED'),('unowned','FAILED'),('matching','SUCCEEDED'),('missing_group','SUCCEEDED')])
def test_multi_destination_installation_http(installation_sim, scope, manager, admin, installation, mode, expected):
    from apps.firewalls.models import Firewall, VDOM
    from apps.firewalls.groups import save_firewall_group
    from apps.accounts.models import GroupGrant
    from apps.changes.installations import submit_installation, decide_installation
    from apps.changes.executor import execute_next
    from apps.changes.models import InstalledResource
    httpx.post(installation_sim+'/__reset',json={'mode':mode},trust_env=False).raise_for_status()
    fw = Firewall(name='Second',hostname='192.0.2.2',allowed_namespace='portal_')
    fw.set_token('test-secret'); fw.save()
    vd = VDOM.objects.create(firewall=fw,name='root')
    for user,caps in [(manager,['view','submit']), (scope[1],['view','approve'])]:
        for cap in caps: GroupGrant.objects.create(user=user,firewall_group=group_for(vd),capability=cap)
    group = save_firewall_group(actor=admin,name='Both',vdom_ids=[scope[2].pk,vd.pk])
    for user,caps in [(manager,['view','submit']),(scope[1],['view','approve'])]:
        for cap in caps: GroupGrant.objects.create(user=user,firewall_group=group,capability=cap)
    item = submit_installation(actor=manager,object_ids=[],group_ids=[installation[2].pk],target_kind='firewall_group',firewall_group_id=group.pk,idempotency_key='http')
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    result = execute_next(owner_id='http-worker')
    assert result.execution_status == expected
    state = httpx.get(installation_sim+'/__state',trust_env=False).json()
    assert set(state['devices']) == {'192.0.2.1','192.0.2.2'}
    if mode in ('success','missing_group','matching'):
        assert item.targets.filter(execution_status='SUCCEEDED').count() == 2
        for device in state['devices'].values():
            assert {'name':'portal_host'} in device['groups']['portal_group']['member']
            if mode != 'missing_group': assert {'name':'existing'} in device['groups']['portal_group']['member']
    if mode == 'matching': assert not InstalledResource.objects.filter(resource_type='address').exists()
    writes = sum(x['writes'] for x in state['devices'].values())
    assert execute_next(owner_id='http-worker') is None
    assert sum(x['writes'] for x in httpx.get(installation_sim+'/__state',trust_env=False).json()['devices'].values()) == writes


def test_usage_scan_over_http_keeps_local_intersection_and_one_result(installation_sim,scope,manager,monkeypatch):
    from apps.fortinet.client import FortinetClient
    from apps.inventory.catalog import save_address
    from apps.inventory import services
    from apps.inventory.models import InventoryScan
    from apps.audit.models import AuditEvent
    httpx.post(installation_sim+'/__reset',json={'mode':'success'},trust_env=False).raise_for_status()
    save_address(actor=manager,name='portal_local',kind='subnet',value='192.0.2.1')
    factory=lambda fw,vd:FortinetClient(fw,vd,transport=SimulationTransport(installation_sim))
    monkeypatch.setattr(services,'FortinetClient',factory)
    with factory(scope[2].firewall,scope[2]) as client:
        for name in ['portal_local','remote_only']:
            client.create_address({'name':name,'type':'ipmask','subnet':'192.0.2.1 255.255.255.255'})
    first=services.scan_usage(actor=manager,vdom=scope[2])
    second=services.scan_usage(actor=manager,vdom=scope[2])
    assert second.findings=={'portal_local':'potentially_unused'}
    assert first.pk==second.pk and InventoryScan.objects.count()==1
    assert AuditEvent.objects.filter(event_type='inventory.scanned').count()==2


def test_superadministrator_self_approved_installation_over_http(installation_sim,installation,scope):
    from apps.changes.installations import decide_installation
    from apps.changes.executor import execute_next
    actor=scope[0]; actor.is_superuser=True; actor.save()
    httpx.post(installation_sim+'/__reset',json={'mode':'success'},trust_env=False).raise_for_status()
    item=decide_installation(actor=actor,request_id=installation[0].pk,status='APPROVED')
    assert item.self_approved and item.approver_id==actor.pk
    result=execute_next(owner_id='self-http')
    assert result.execution_status=='SUCCEEDED'
    state=httpx.get(installation_sim+'/__state',trust_env=False).json()
    assert state['devices']['192.0.2.1']['addresses']['portal_host']['name']=='portal_host'


def test_group_usage_over_http_reports_objects_and_groups_without_writes(installation_sim,scope,manager,monkeypatch):
    from apps.fortinet.client import FortinetClient
    from apps.inventory.catalog import save_address,save_address_group
    from apps.inventory import services
    from apps.inventory.models import InventoryScan
    from apps.firewalls.models import Firewall,VDOM,FirewallGroup,FirewallGroupMember
    from apps.accounts.models import GroupGrant
    httpx.post(installation_sim+'/__reset',json={'mode':'success','policies':[{'srcaddr':[{'name':'all'}],'dstaddr':[{'name':'all'}]}]},trust_env=False).raise_for_status()
    class DeviceTransport(SimulationTransport):
        def handle_request(self,request):
            request.headers['x-test-device']=request.url.host
            return super().handle_request(request)
    factory=lambda fw,vd:FortinetClient(fw,vd,transport=DeviceTransport(installation_sim))
    monkeypatch.setattr(services,'FortinetClient',factory)
    fw=Firewall(name='Usage peer',hostname='192.0.2.2'); fw.set_token('test-secret'); fw.save()
    vd=VDOM.objects.create(firewall=fw,name='root')
    group=FirewallGroup.objects.create(name='Usage group')
    for target in (scope[2],vd):
        FirewallGroupMember.objects.create(group=group,firewall=target.firewall,vdom=target)
        with factory(target.firewall,target) as client:
            client.create_address({'name':'portal_usage','type':'ipmask','subnet':'192.0.2.9 255.255.255.255'})
            client.create_group({'name':'portal_usage_group','member':[{'name':'portal_usage'}]})
    GroupGrant.objects.create(user=manager,firewall_group=group,capability='view')
    save_address(actor=manager,name='portal_usage',kind='subnet',value='192.0.2.9')
    save_address_group(actor=manager,name='portal_usage_group',member_ids=[])
    before=httpx.get(installation_sim+'/__state',trust_env=False).json()
    writes=sum(device['writes'] for device in before['devices'].values())
    for _ in range(2): scans=services.scan_group_usage(actor=manager,firewall_group_id=group.pk)
    assert len(scans)==2 and InventoryScan.objects.count()==2
    for scan in scans:
        assert scan.complete and scan.findings=={'portal_usage':'potentially_unused'}
        assert scan.group_findings=={'portal_usage_group':'potentially_unused'}
    after=httpx.get(installation_sim+'/__state',trust_env=False).json()
    assert sum(device['writes'] for device in after['devices'].values())==writes


@pytest.mark.parametrize('kind,value',[('fqdn','host.example.invalid'),('wildcard_fqdn','*.example.invalid'),('subnet','192.0.2.0/27')])
def test_address_types_with_exact_names_over_http(installation_sim,scope,kind,value):
    from apps.fortinet.client import FortinetClient
    from apps.fortinet.schemas import address_payload
    httpx.post(installation_sim+'/__reset',json={'mode':'success'},trust_env=False).raise_for_status()
    payload=address_payload('check_'+value,kind,value)
    with FortinetClient(scope[2].firewall,scope[2],transport=SimulationTransport(installation_sim)) as client:
        client.create_address(payload)
        assert all(client.get_address(payload['name']).get(k)==v for k,v in payload.items())
        client.update_address(payload['name'],payload)
        assert all(client.get_address(payload['name']).get(k)==v for k,v in payload.items())
        client.delete_address(payload['name'])
        assert client.get_address(payload['name']) is None


def test_validated_device_installs_all_address_types_over_http(installation_sim,scope,manager,monkeypatch):
    from apps.fortinet.capabilities import require_write_capability
    from apps.changes import installation_executor
    from apps.inventory.catalog import save_address,save_address_group
    from apps.changes.installations import submit_installation,decide_installation
    from apps.changes.executor import execute_next
    fw=scope[2].firewall
    fw.hostname='192.168.100.38'; fw.protocol='http'; fw.port=80; fw.observed_version='v7.0.13'; fw.save()
    monkeypatch.setattr(installation_executor,'require_write_capability',require_write_capability)
    httpx.post(installation_sim+'/__reset',json={'mode':'success'},trust_env=False).raise_for_status()
    definitions=[('fqdn','host.example.invalid'),('wildcard_fqdn','*.example.invalid'),('subnet','192.0.2.0/27')]
    objects=[save_address(actor=manager,name='portal_'+value,kind=kind,value=value) for kind,value in definitions]
    group=save_address_group(actor=manager,name='portal_types',member_ids=[obj.pk for obj in objects])
    item=submit_installation(actor=manager,object_ids=[],group_ids=[group.pk],target_kind='firewall_group',firewall_group_id=group_for(scope[2]).pk,idempotency_key='validated-types-http')
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    result=execute_next(owner_id='validated-types-http')
    assert result.execution_status=='SUCCEEDED'
    state=httpx.get(installation_sim+'/__state',trust_env=False).json()['devices']['192.168.100.38']
    assert {m['name'] for m in state['groups']['portal_types']['member']}=={obj.entry.name for obj in objects}
    for kind,value in definitions:
        assert state['addresses']['portal_'+value]['type']==('ipmask' if kind=='subnet' else 'fqdn')
