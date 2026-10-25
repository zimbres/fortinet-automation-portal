import os
import httpx
import pytest
from django.core.exceptions import PermissionDenied

pytestmark = [pytest.mark.django_db, pytest.mark.skipif(not os.environ.get('FORTINET_SIMULATION_URL'), reason='Start the local HTTP simulation and set FORTINET_SIMULATION_URL.')]


class SimulationTransport(httpx.BaseTransport):
    """Test-only network routing; production client configuration is unchanged."""
    def __init__(self, base):
        self.base = base
        self.transport = httpx.HTTPTransport()

    def handle_request(self, request):
        url = httpx.URL(self.base + request.url.path).copy_with(query=request.url.query)
        rewritten = httpx.Request(request.method,url,headers=request.headers,content=request.read())
        return self.transport.handle_request(rewritten)

    def close(self): self.transport.close()


@pytest.fixture
def simulation(monkeypatch):
    from apps.fortinet.client import FortinetClient
    import apps.changes.executor as executor
    base = os.environ['FORTINET_SIMULATION_URL']
    monkeypatch.setattr(executor,'require_write_capability',lambda *args: None)
    monkeypatch.setattr(executor,'FortinetClient',lambda fw,vd:FortinetClient(fw,vd,transport=SimulationTransport(base)))
    return base


@pytest.mark.parametrize('mode,expected,writes', [
    ('success','SUCCEEDED',2), ('reject','FAILED',0),
    ('uncertain','RECONCILIATION_REQUIRED',1), ('partial','FAILED',1), ('conflict','FAILED',1),
    ('read_failure','RECONCILIATION_REQUIRED',1), ('invalid_group','FAILED',0),
])
def test_approved_flow_over_real_http(scope, simulation, mode, expected, writes):
    from apps.changes.services import approve_change
    from tests.legacy_helpers import legacy_request
    from apps.changes.executor import execute_next
    from apps.audit.models import AuditEvent
    httpx.post(simulation+'/__reset',json={'mode':mode},trust_env=False).raise_for_status()
    operator,approver,vdom = scope
    item = legacy_request(actor=operator,vdom=vdom,operation='add_group_member',idempotency_key='http-flow',
        payload={'name':'portal_host','kind':'subnet','value':'192.0.2.1','group':'unauthorized' if mode == 'invalid_group' else 'portal_group','create_new':True})
    with pytest.raises(PermissionDenied): approve_change(actor=operator,request_id=item.pk)
    approve_change(actor=approver,request_id=item.pk)
    execute_next(owner_id='integration-worker')
    item.refresh_from_db()
    assert item.execution_status == expected
    state = httpx.get(simulation+'/__state',trust_env=False).json()
    assert state['writes'] == writes
    if mode == 'success':
        assert state['groups']['portal_group']['member'] == [{'name':'existing'},{'name':'portal_host'}]
    if mode in ('partial','uncertain','conflict'):
        assert state['addresses']['portal_host']['subnet'] == '192.0.2.1 255.255.255.255'
    assert AuditEvent.objects.filter(event_type='change.execution_finished').exists()
    assert execute_next(owner_id='integration-worker') is None
    assert httpx.get(simulation+'/__state',trust_env=False).json()['writes'] == writes
