import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from apps.accounts.models import User
from apps.firewalls.models import Firewall, VDOM, FirewallGroup, FirewallGroupMember

pytestmark = pytest.mark.django_db


def setup_group(name='Branches'):
    group = FirewallGroup.objects.create(name=name)
    fw = Firewall.objects.create(name=name,hostname='192.0.2.1')
    vd = VDOM.objects.create(firewall=fw,name='root')
    FirewallGroupMember.objects.create(group=group,firewall=fw,vdom=vd)
    return group,vd


def test_group_grant_controls_member_visibility_and_revocation():
    from apps.accounts.models import GroupGrant
    from apps.accounts.permissions import visible_vdoms, require_capability
    group,vd=setup_group()
    user=User.objects.create_user('member')
    grant=GroupGrant.objects.create(user=user,firewall_group=group,capability='view')
    assert list(visible_vdoms(user)) == [vd]
    require_capability(user,vd,'view')
    grant.delete()
    with pytest.raises(PermissionDenied): require_capability(user,vd,'view')


def test_group_update_cannot_orphan_firewall():
    from apps.firewalls.groups import save_firewall_group
    group,vd=setup_group()
    admin=User.objects.create_user('admin',is_superuser=True)
    with pytest.raises(ValidationError):
        save_firewall_group(actor=admin,group_id=group.pk,name=group.name,vdom_ids=[])
    assert group.members.filter(vdom=vd).exists()


def test_first_group_can_be_empty():
    from apps.firewalls.groups import save_firewall_group
    admin=User.objects.create_user('admin',is_superuser=True)
    assert save_firewall_group(actor=admin,name='First',vdom_ids=[]).name == 'First'


def test_direct_request_target_is_rejected(scope):
    from apps.firewalls.groups import resolve_destinations
    with pytest.raises(ValidationError):
        resolve_destinations(actor=scope[0],target_kind='firewall',vdom_id=scope[2].pk)


def test_cancel_installation_cancels_execution_and_targets(installation,scope):
    from apps.changes.installations import decide_installation, refresh_installation_status
    item=decide_installation(actor=scope[0],request_id=installation[0].pk,status='CANCELLED')
    assert item.execution_status == 'CANCELLED'
    assert item.finished_at
    assert set(item.targets.values_list('execution_status',flat=True)) == {'CANCELLED'}
    assert refresh_installation_status(item.pk).execution_status == 'CANCELLED'


from tests.test_installations import installation
from tests.test_catalog import manager

def test_group_update_cannot_replace_last_member_with_other_firewall():
    from apps.firewalls.groups import save_firewall_group
    group,vd=setup_group()
    other_fw=Firewall.objects.create(name='Other',hostname='192.0.2.2')
    other=VDOM.objects.create(firewall=other_fw,name='root')
    admin=User.objects.create_user('admin',is_superuser=True)
    with pytest.raises(ValidationError):
        save_firewall_group(actor=admin,group_id=group.pk,name=group.name,vdom_ids=[other.pk])
    assert group.members.filter(vdom=vd).exists()


def test_overlapping_group_permission_cannot_authorize_selected_group(scope):
    from apps.firewalls.groups import resolve_destinations
    group=FirewallGroup.objects.create(name='Same firewall, different authorization')
    FirewallGroupMember.objects.create(group=group,firewall=scope[2].firewall,vdom=scope[2])
    with pytest.raises(PermissionDenied):
        resolve_destinations(actor=scope[0],target_kind='firewall_group',firewall_group_id=group.pk)


def test_approved_pending_installation_can_be_cancelled_and_never_claimed(installation,scope):
    from apps.changes.installations import decide_installation
    from apps.changes.installation_executor import execute_next_installation
    item=installation[0]
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    item=decide_installation(actor=scope[0],request_id=item.pk,status='CANCELLED')
    assert item.execution_status == 'CANCELLED'
    assert execute_next_installation(owner_id='cancel-test') is None


def test_running_installation_cannot_be_cancelled(installation,scope):
    from apps.changes.installations import decide_installation
    from apps.changes.models import InstallationRequest
    item=installation[0]
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    InstallationRequest.objects.filter(pk=item.pk).update(execution_status='RUNNING')
    with pytest.raises(ValidationError):
        decide_installation(actor=scope[0],request_id=item.pk,status='CANCELLED')
    item.refresh_from_db()
    assert item.approval_status == 'APPROVED'

def test_legacy_direct_submission_is_disabled(scope):
    from apps.changes.services import submit_change
    with pytest.raises(ValidationError):
        submit_change(actor=scope[0],vdom=scope[2],operation='create_address',payload={'name':'portal_old','kind':'subnet','value':'192.0.2.1'},idempotency_key='direct')

def test_firewall_registration_requires_group_and_is_atomic(scope,settings):
    from apps.firewalls.services import register_firewall
    user=scope[0]; user.is_superuser=True; user.save()
    before=Firewall.objects.count()
    with pytest.raises(ValidationError):
        register_firewall(actor=user,name='New',hostname='192.0.2.2',port=80,token='local-test',allowed_namespace='',firewall_groups=[],protocol='http')
    assert Firewall.objects.count() == before


def test_group_permissions_cannot_be_borrowed_during_execution(installation,scope):
    from apps.accounts.models import GroupGrant
    from apps.changes.installations import decide_installation,check_installation_authorization
    item=installation[0]
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    group=FirewallGroup.objects.create(name='Overlapping')
    FirewallGroupMember.objects.create(group=group,firewall=scope[2].firewall,vdom=scope[2])
    for cap in ('view','submit'): GroupGrant.objects.create(user=scope[0],firewall_group=group,capability=cap)
    GroupGrant.objects.filter(user=scope[0],firewall_group_id=item.snapshot['firewall_group_id'],capability='submit').delete()
    with pytest.raises(PermissionDenied): check_installation_authorization(item.targets.get())


def test_removed_group_destination_revokes_execution(installation,scope):
    from apps.changes.installations import decide_installation,check_installation_authorization
    item=installation[0]
    decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    FirewallGroupMember.objects.filter(group_id=item.snapshot['firewall_group_id']).delete()
    with pytest.raises(PermissionDenied): check_installation_authorization(item.targets.get())


def test_legacy_cancel_sets_execution_terminal(scope):
    from tests.legacy_helpers import legacy_request
    from apps.changes.services import approve_change,cancel_change
    item=legacy_request(actor=scope[0],vdom=scope[2],operation='create_address',payload={'name':'portal_legacy','kind':'subnet','value':'192.0.2.1'},idempotency_key='history')
    approve_change(actor=scope[1],request_id=item.pk)
    item=cancel_change(actor=scope[0],request_id=item.pk)
    assert item.execution_status=='CANCELLED' and item.finished_at

def test_approval_rechecks_requester_exact_group_permission(installation,scope):
    from apps.accounts.models import GroupGrant
    from apps.changes.installations import decide_installation
    item=installation[0]
    overlapping=FirewallGroup.objects.create(name='Other authorization')
    FirewallGroupMember.objects.create(group=overlapping,firewall=scope[2].firewall,vdom=scope[2])
    for cap in ('view','submit'): GroupGrant.objects.create(user=scope[0],firewall_group=overlapping,capability=cap)
    GroupGrant.objects.filter(user=scope[0],firewall_group_id=item.snapshot['firewall_group_id'],capability='submit').delete()
    with pytest.raises(PermissionDenied):
        decide_installation(actor=scope[1],request_id=item.pk,status='APPROVED')
    item.refresh_from_db()
    assert item.approval_status=='PENDING'

def test_firewall_list_does_not_reveal_ungranted_group_names(client,scope):
    secret=FirewallGroup.objects.create(name='Confidential group')
    FirewallGroupMember.objects.create(group=secret,firewall=scope[2].firewall,vdom=scope[2])
    client.force_login(scope[0])
    page=client.get('/firewalls/')
    assert page.status_code==200
    assert b'Confidential group' not in page.content
