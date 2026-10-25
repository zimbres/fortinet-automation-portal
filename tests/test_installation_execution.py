import copy
import json
import httpx
import pytest
from tests.test_catalog import manager
from tests.test_installations import installation

pytestmark = pytest.mark.django_db


@pytest.fixture
def device(monkeypatch, installation, scope):
    from apps.changes.installations import decide_installation
    from apps.changes.executor import acquire_lease
    from apps.changes import installation_executor as executor
    from apps.fortinet.client import FortinetClient
    state = {'addresses': {}, 'groups': {'portal_group': {'name':'portal_group', 'member':[{'name':'external'}]}}, 'calls': [], 'mode':'success'}
    def respond(req):
        state['calls'].append((req.method, req.url.path))
        resource = 'addresses' if '/address' in req.url.path and '/addrgrp' not in req.url.path else 'groups'
        name = req.url.path.split('/')[-1]
        if req.method == 'GET':
            if state['mode'] == 'bad_read' and any(m != 'GET' for m,p in state['calls']): return httpx.Response(200,json={'status':'success','results':'bad'})
            if state['mode'] == 'bad_group_read' and resource == 'groups' and any(m == 'POST' and p.endswith('/addrgrp') for m,p in state['calls']): return httpx.Response(200,json={'status':'success','results':'bad'})
            value = state[resource].get(name)
            return httpx.Response(200 if value else 404,json={'status':'success' if value else 'error','results':[copy.deepcopy(value)] if value else []})
        if state['mode'] == 'reject': return httpx.Response(403,json={'status':'error'})
        if state['mode'] == 'partial' and resource == 'groups': return httpx.Response(403,json={'status':'error'})
        payload = json.loads(req.content)
        state[resource][payload['name'] if req.method == 'POST' else name] = payload
        if state.get('after_write'): state['after_write'](req)
        return httpx.Response(200,json={'status':'success'})
    monkeypatch.setattr(executor,'FortinetClient',lambda fw,vd:FortinetClient(fw,vd,transport=httpx.MockTransport(respond)))
    from apps.changes import installation_reconciliation
    monkeypatch.setattr(installation_reconciliation,'FortinetClient',lambda fw,vd:FortinetClient(fw,vd,transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(executor,'require_write_capability',lambda *args:None)
    decide_installation(actor=scope[1], request_id=installation[0].pk, status='APPROVED')
    acquire_lease('worker')
    return state


def run_target(installation):
    from apps.changes.installation_executor import execute_installation_target
    return execute_installation_target(target_id=installation[0].targets.get().pk, owner_id='worker')


def test_dependencies_before_groups_and_preserved_members(installation, device):
    target = run_target(installation)
    assert target.execution_status == 'SUCCEEDED'
    assert device['groups']['portal_group']['member'] == [{'name':'external'},{'name':'portal_host'}]
    assert [m for m,p in device['calls'] if m != 'GET'] == ['POST','PUT']
    assert target.steps.filter(result='SUCCEEDED').count() == 2


def test_preflight_unowned_conflict_no_writes(installation, device):
    device['addresses']['portal_host'] = {'name':'portal_host','type':'ipmask','subnet':'192.0.2.9 255.255.255.255'}
    assert run_target(installation).execution_status == 'FAILED'
    assert all(m == 'GET' for m,p in device['calls'])


def test_identical_noop_does_not_adopt_ownership(installation, device):
    from apps.changes.models import InstalledResource
    device['addresses']['portal_host'] = {'name':'portal_host','type':'ipmask','subnet':'192.0.2.1 255.255.255.255'}
    assert run_target(installation).execution_status == 'SUCCEEDED'
    assert not InstalledResource.objects.filter(resource_type='address').exists()
    assert [m for m,p in device['calls'] if m != 'GET'] == ['PUT']


@pytest.mark.parametrize('mode,expected',[('partial','FAILED'),('bad_read','RECONCILIATION_REQUIRED')])
def test_partial_and_malformed_readback(installation, device, mode, expected):
    device['mode'] = mode
    assert run_target(installation).execution_status == expected
    assert device['addresses']['portal_host']


def test_missing_group_creation_and_namespace_preflight(installation, device):
    device['groups'] = {}
    assert run_target(installation).execution_status == 'SUCCEEDED'
    assert [m for m,p in device['calls'] if m != 'GET'] == ['POST','POST']


def test_owned_update_and_authorization_revocation(installation, device, scope):
    from apps.changes.models import InstalledResource
    from apps.accounts.models import GroupGrant
    target = installation[0].targets.get()
    InstalledResource.objects.create(vdom=scope[2], resource_type='address', name='portal_host', originating_target=target)
    device['addresses']['portal_host'] = {'name':'portal_host','type':'ipmask','subnet':'192.0.2.9 255.255.255.255'}
    GroupGrant.objects.filter(user=scope[1],capability='approve').delete()
    assert run_target(installation).execution_status == 'FAILED'
    assert not device['calls']


def test_disabled_scope_after_preflight_blocks_later_writes(installation, device, scope):
    from apps.firewalls.models import Firewall
    def disable(req):
        Firewall.objects.filter(pk=scope[2].firewall_id).update(enabled=False)
    device['after_write'] = disable
    target = run_target(installation)
    assert target.execution_status == 'FAILED'
    assert [m for m,p in device['calls'] if m != 'GET'] == ['POST']


def test_opposite_namespace_conflict_blocks_all_writes(installation, device):
    device['addresses']['portal_group'] = {'name':'portal_group','type':'ipmask','subnet':'192.0.2.9 255.255.255.255'}
    device['groups'] = {}
    assert run_target(installation).execution_status == 'FAILED'
    assert all(m == 'GET' for m,p in device['calls'])


def test_recreating_previously_owned_group_preserves_provenance(installation, device, scope):
    from apps.changes.models import InstalledResource
    target = installation[0].targets.get()
    owned = InstalledResource.objects.create(vdom=scope[2],resource_type='group',name='portal_group',originating_target=target)
    device['groups'] = {}
    assert run_target(installation).execution_status == 'SUCCEEDED'
    assert InstalledResource.objects.filter(vdom=scope[2],resource_type='group',name='portal_group').count() == 1


def test_noop_address_must_still_match_before_success(installation, device, monkeypatch):
    from apps.changes import installation_executor
    device['addresses']['portal_host'] = {'name':'portal_host','type':'ipmask','subnet':'192.0.2.1 255.255.255.255'}
    preflight = installation_executor.preflight_installation
    def drift(target, client):
        plan = preflight(target,client)
        device['addresses']['portal_host']['subnet'] = '192.0.2.99 255.255.255.255'
        return plan
    monkeypatch.setattr(installation_executor,'preflight_installation',drift)
    assert run_target(installation).execution_status == 'FAILED'
    assert all(m == 'GET' for m,p in device['calls'])


def test_group_installation_requires_no_firewall_allowlist(installation, device, scope):
    # The approved local catalog group itself determines the group to install.
    from apps.firewalls.models import Firewall
    assert not hasattr(Firewall.objects.get(pk=scope[2].firewall_id),'allowed_groups')
    assert run_target(installation).execution_status == 'SUCCEEDED'


def test_firewall_can_install_without_object_prefix(installation, device, scope):
    from apps.firewalls.models import Firewall
    Firewall.objects.filter(pk=scope[2].firewall_id).update(allowed_namespace='')
    assert run_target(installation).execution_status == 'SUCCEEDED'


def test_client_destination_change_cannot_inherit_validated_scope(installation, device, scope, monkeypatch):
    from apps.changes import installation_executor
    from apps.fortinet.capabilities import require_write_capability
    from apps.firewalls.models import Firewall
    factory = installation_executor.FortinetClient
    def change_after_client_creation(firewall, vdom):
        client = factory(firewall,vdom)
        Firewall.objects.filter(pk=firewall.pk).update(protocol='http',hostname='192.168.100.38',port=80,observed_version='v7.0.13')
        return client
    monkeypatch.setattr(installation_executor,'FortinetClient',change_after_client_creation)
    monkeypatch.setattr(installation_executor,'require_write_capability',require_write_capability)
    assert run_target(installation).execution_status == 'FAILED'
    assert all(method == 'GET' for method,path in device['calls'])
