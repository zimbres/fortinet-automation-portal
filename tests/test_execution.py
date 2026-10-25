from datetime import timedelta
import pytest
from django.utils import timezone
from apps.changes.services import approve_change
from tests.legacy_helpers import legacy_request
from apps.changes.executor import execute_next,acquire_lease
from apps.changes.models import ChangeRequest,ExecutorLease
from apps.fortinet.exceptions import FortinetError
from apps.accounts.models import GroupGrant

pytestmark = pytest.mark.django_db


def approved(scope):
    item = legacy_request(actor=scope[0],vdom=scope[2],operation='create_address',idempotency_key='exec',
        payload={'name':'portal_host','kind':'subnet','value':'192.0.2.1'})
    approve_change(actor=scope[1],request_id=item.pk)
    return item


def test_active_lease_blocks_second_executor():
    acquire_lease('first')
    with pytest.raises(FortinetError): acquire_lease('second')


def test_expired_claim_requires_reconciliation(scope):
    item = approved(scope)
    ChangeRequest.objects.filter(pk=item.pk).update(execution_status='RUNNING')
    ExecutorLease.objects.create(pk=1,owner='dead',expires_at=timezone.now()-timedelta(seconds=1))
    assert execute_next(owner_id='new') is None
    item.refresh_from_db()
    assert item.execution_status == 'RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('actor_index,capability',[(0,'submit'),(1,'approve')])
def test_revoked_permission_blocks_approved_execution(scope,actor_index,capability):
    item = approved(scope)
    GroupGrant.objects.filter(user=scope[actor_index],capability=capability).delete()
    execute_next(owner_id='worker')
    item.refresh_from_db()
    assert item.execution_status == 'FAILED'
    assert 'permission' in item.error_message


def test_malformed_post_write_membership_is_uncertain(scope,monkeypatch):
    import apps.changes.executor as executor
    item = legacy_request(actor=scope[0],vdom=scope[2],operation='add_group_member',idempotency_key='malformed-group',
        payload={'name':'existing_host','group':'portal_group','create_new':False})
    approve_change(actor=scope[1],request_id=item.pk)
    class Remote:
        changed = False
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get_address(self,name): return {'name':name}
        def get_group(self,name): return {'name':name,'member':'invalid' if self.changed else [{'name':'other'}]}
        def set_group_members(self,name,members): self.changed = True
    remote = Remote()
    monkeypatch.setattr(executor,'FortinetClient',lambda *args:remote)
    monkeypatch.setattr(executor,'require_write_capability',lambda *args:None)
    execute_next(owner_id='worker')
    item.refresh_from_db()
    assert remote.changed
    assert item.execution_status == 'RECONCILIATION_REQUIRED'
