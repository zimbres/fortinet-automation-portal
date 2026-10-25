import pytest
from django.core.exceptions import PermissionDenied
from apps.accounts.models import User,GroupGrant
from apps.accounts.permissions import require_group_capability,require_capability,visible_vdoms
from apps.firewalls.groups import visible_firewall_groups
from tests.test_installations import installation
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def test_superadmins_submit_and_approve_without_explicit_grants(scope,client):
    from apps.inventory.catalog import save_address
    from apps.changes.installations import submit_installation,decide_installation,check_installation_authorization,installations_for
    from tests.group_helpers import group_for
    first=User.objects.create_user('first_admin',is_superuser=True)
    second=User.objects.create_user('second_admin',is_superuser=True)
    group=group_for(scope[2])
    assert not GroupGrant.objects.filter(user__in=[first,second]).exists()
    assert visible_firewall_groups(first,'submit').filter(pk=group.pk).exists()
    assert visible_vdoms(first,'submit').filter(pk=scope[2].pk).exists()
    obj=save_address(actor=first,name='portal_admin',kind='subnet',value='192.0.2.8')
    item=submit_installation(actor=first,object_ids=[obj.pk],group_ids=[],target_kind='firewall_group',firewall_group_id=group.pk,idempotency_key='superadmin')
    assert installations_for(second,'approve').filter(pk=item.pk).exists()
    client.force_login(second)
    assert client.get(f'/installations/{item.pk}/').context['can_approve']
    decide_installation(actor=second,request_id=item.pk,status='APPROVED')
    check_installation_authorization(item.targets.get())


def test_superadmin_status_is_rechecked_and_disabled_groups_are_denied(scope):
    from tests.group_helpers import group_for
    admin=User.objects.create_user('admin',is_superuser=True)
    group=group_for(scope[2])
    require_group_capability(admin,group.pk,'submit')
    require_capability(admin,scope[2],'approve')
    User.objects.filter(pk=admin.pk).update(is_superuser=False)
    with pytest.raises(PermissionDenied): require_group_capability(admin,group.pk,'submit')
    assert not visible_firewall_groups(admin,'approve').exists()
    assert not visible_vdoms(admin,'submit').exists()
    User.objects.filter(pk=admin.pk).update(is_superuser=True)
    group.enabled=False; group.save()
    with pytest.raises(PermissionDenied): require_group_capability(admin,group.pk,'approve')
    assert not visible_firewall_groups(admin,'approve').filter(pk=group.pk).exists()


def test_inactive_superadmin_and_unknown_permissions_are_denied(scope):
    from tests.group_helpers import group_for
    admin=User.objects.create_user('inactive_admin',is_superuser=True)
    group=group_for(scope[2])
    with pytest.raises(PermissionDenied): require_group_capability(admin,group.pk,'invalid')
    User.objects.filter(pk=admin.pk).update(is_active=False)
    with pytest.raises(PermissionDenied): require_group_capability(admin,group.pk,'submit')
    assert not visible_firewall_groups(admin,'approve').exists()
    assert not visible_vdoms(admin,'submit').exists()

def test_disabled_group_cannot_borrow_enabled_membership(scope):
    from apps.firewalls.models import FirewallGroup,FirewallGroupMember
    user=scope[0]
    GroupGrant.objects.filter(user=user).delete()
    group=FirewallGroup.objects.create(name='Disabled grant',enabled=False)
    FirewallGroupMember.objects.create(group=group,firewall=scope[2].firewall,vdom=scope[2])
    GroupGrant.objects.create(user=user,firewall_group=group,capability='view')
    assert not visible_vdoms(user).exists()
    with pytest.raises(PermissionDenied): require_capability(user,scope[2],'view')

def test_user_access_page_explains_automatic_superadmin_permissions(client,scope):
    admin=User.objects.create_user('automatic_admin',is_superuser=True)
    client.force_login(admin)
    page=client.get('/users/')
    assert b'All enabled groups' in page.content

def test_superadmin_administer_stays_explicit_and_uses_automatic_view(scope):
    from tests.group_helpers import group_for
    admin=User.objects.create_user('scoped_administrator',is_superuser=True)
    group=group_for(scope[2])
    with pytest.raises(PermissionDenied): require_group_capability(admin,group.pk,'administer')
    assert not visible_firewall_groups(admin,'administer').exists()
    GroupGrant.objects.create(user=admin,firewall_group=group,capability='administer')
    require_group_capability(admin,group.pk,'administer')
    assert visible_firewall_groups(admin,'administer').filter(pk=group.pk).exists()
