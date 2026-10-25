import pytest
from django.core.exceptions import PermissionDenied
from apps.accounts.models import User,GroupGrant
from tests.test_installations import installation
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def test_superadmin_self_approval_reaches_executor_and_own_queue(installation,scope,client):
    from apps.changes.installations import decide_installation,check_installation_authorization
    actor=scope[0]; actor.is_superuser=True; actor.save()
    item=installation[0]
    GroupGrant.objects.filter(user=actor).delete()
    client.force_login(actor)
    page=client.get(f'/installations/{item.pk}/')
    assert page.context['can_approve']
    assert b'Approve installation' in page.content and b'>Reject<' not in page.content
    assert str(item.pk).encode() in client.get('/approvals/').content
    assert client.post(f'/installations/{item.pk}/approve/').status_code==302
    item.refresh_from_db()
    approved=item
    assert b'self-approved as superadministrator' in client.get(f'/installations/{item.pk}/').content
    assert approved.approver_id==actor.pk and approved.self_approved
    check_installation_authorization(item.targets.get())
    from apps.audit.models import AuditEvent
    assert AuditEvent.objects.filter(event_type='installation.approved',actor=actor,metadata__self_approved=True).exists()


def test_self_approval_exception_is_revoked_on_demotion_even_with_grants(installation,scope):
    from apps.changes.installations import decide_installation,check_installation_authorization
    actor=scope[0]; actor.is_superuser=True; actor.save()
    item=decide_installation(actor=actor,request_id=installation[0].pk,status='APPROVED')
    from tests.group_helpers import group_for
    GroupGrant.objects.create(user=actor,firewall_group=group_for(scope[2]),capability='approve')
    User.objects.filter(pk=actor.pk).update(is_superuser=False)
    with pytest.raises(PermissionDenied): check_installation_authorization(item.targets.get())


def test_stale_superadmin_cannot_self_approve_after_demotion(installation,scope):
    from apps.changes.installations import decide_installation
    actor=scope[0]; actor.is_superuser=True; actor.save()
    User.objects.filter(pk=actor.pk).update(is_superuser=False)
    with pytest.raises(PermissionDenied): decide_installation(actor=actor,request_id=installation[0].pk,status='APPROVED')


def test_legacy_superadmin_self_approval_and_authorization(scope):
    from tests.legacy_helpers import legacy_request
    from apps.changes.services import approve_change
    from apps.changes.executor import check_authorization
    actor=scope[0]; actor.is_superuser=True; actor.save()
    item=legacy_request(actor=actor,vdom=scope[2],operation='create_address',payload={'name':'portal_old','kind':'subnet','value':'192.0.2.1'},idempotency_key='self')
    item=approve_change(actor=actor,request_id=item.pk)
    assert item.self_approved and item.approver_id==actor.pk
    check_authorization(item)
