from tests.group_helpers import group_for
import pytest
from apps.accounts.models import GroupGrant
from apps.changes.models import ChangeRequest,ExecutionStep,ObjectReference
from apps.changes.services import approve_change
from tests.legacy_helpers import legacy_request

pytestmark = pytest.mark.django_db


def test_reconciliation_does_not_certify_missing_unrelated_members(scope,monkeypatch):
    from apps.changes import reconciliation
    operator,approver,vdom = scope
    GroupGrant.objects.create(user=approver,firewall_group=group_for(vdom),capability='administer')
    item = legacy_request(actor=operator,vdom=vdom,operation='add_group_member',idempotency_key='reconcile-group',
        payload={'name':'portal_host','group':'portal_group','create_new':False})
    approve_change(actor=approver,request_id=item.pk)
    ChangeRequest.objects.filter(pk=item.pk).update(execution_status='RECONCILIATION_REQUIRED')
    ExecutionStep.objects.create(request=item,step_type='group_intent',result='PREPARED',after_state={
        'name':'portal_group','member':[{'name':'existing'},{'name':'portal_host'}]})
    class Remote:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get_address(self,name): return {'name':name}
        def get_group(self,name): return {'name':name,'member':[{'name':'portal_host'}]}
    monkeypatch.setattr(reconciliation,'FortinetClient',lambda *args:Remote())
    result = reconciliation.reconcile_change(actor=approver,request_id=item.pk)
    assert result.execution_status == 'RECONCILIATION_REQUIRED'


def test_confirmed_creation_restores_ownership(scope,monkeypatch):
    from apps.changes import reconciliation
    operator,approver,vdom = scope
    GroupGrant.objects.create(user=approver,firewall_group=group_for(vdom),capability='administer')
    item = legacy_request(actor=operator,vdom=vdom,operation='create_address',idempotency_key='reconcile-create',
        payload={'name':'portal_host','kind':'subnet','value':'192.0.2.1'})
    approve_change(actor=approver,request_id=item.pk)
    ChangeRequest.objects.filter(pk=item.pk).update(execution_status='RECONCILIATION_REQUIRED')
    class Remote:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get_address(self,name): return {'name':name,'type':'ipmask','subnet':'192.0.2.1 255.255.255.255'}
    monkeypatch.setattr(reconciliation,'FortinetClient',lambda *args:Remote())
    result = reconciliation.reconcile_change(actor=approver,request_id=item.pk)
    assert result.execution_status == 'SUCCEEDED'
    assert ObjectReference.objects.filter(vdom=vdom,name='portal_host',originating_request=item).exists()
