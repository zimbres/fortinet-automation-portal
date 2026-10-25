from tests.group_helpers import group_for
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

pytestmark = pytest.mark.django_db


def submit(scope, key='one', **extra):
    from tests.legacy_helpers import legacy_request
    operator, _, vdom = scope
    return legacy_request(actor=operator, vdom=vdom, operation='create_address',
        payload={'name':'portal_host','kind':'subnet','value':'192.0.2.1', **extra}, idempotency_key=key)


def test_regular_user_self_approval_never_allowed(scope):
    from apps.changes.services import approve_change
    from apps.accounts.models import GroupGrant
    operator, _, vdom = scope
    GroupGrant.objects.create(user=operator, firewall_group=group_for(vdom), capability='approve')
    item = submit(scope)
    with pytest.raises(PermissionDenied): approve_change(actor=operator, request_id=item.pk)
    item.refresh_from_db()
    assert item.approval_status == 'PENDING'


def test_idempotency_and_payload_immutable(scope):
    item = submit(scope)
    item.payload['value'] = '192.0.2.3'
    with pytest.raises(ValidationError): item.save()


def test_approval_and_rejection_transitions(scope):
    from apps.changes.services import approve_change, reject_change
    item = submit(scope)
    approved = approve_change(actor=scope[1], request_id=item.pk)
    assert approved.approval_status == 'APPROVED'
    assert approved.approver_id == scope[1].pk
    with pytest.raises(ValidationError): reject_change(actor=scope[1], request_id=item.pk, reason='no')


def test_unknown_version_blocks_before_network(scope):
    from apps.changes.services import approve_change
    from apps.changes.executor import execute_next
    item = submit(scope)
    approve_change(actor=scope[1], request_id=item.pk)
    execute_next(owner_id='test-worker')
    item.refresh_from_db()
    assert item.execution_status == 'FAILED'
    assert 'not been validated' in item.error_message


def test_unapproved_request_never_claimed(scope):
    from apps.changes.executor import execute_next
    item = submit(scope)
    assert execute_next(owner_id='test-worker') is None
    item.refresh_from_db()
    assert item.execution_status == 'PENDING'
