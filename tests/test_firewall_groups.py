from tests.group_helpers import group_for
import pytest
from django.core.exceptions import ValidationError, PermissionDenied
from apps.accounts.models import User, GroupGrant
from apps.firewalls.models import Firewall, VDOM

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(db):
    return User.objects.create_user('admin', is_superuser=True)


def test_superadmin_only_group_mutations(scope):
    from apps.firewalls.groups import save_firewall_group
    with pytest.raises(PermissionDenied): save_firewall_group(actor=scope[0], name='Branch', vdom_ids=[scope[2].pk])


def test_explicit_vdom_and_unique_firewall(admin, scope):
    from apps.firewalls.groups import save_firewall_group, resolve_destinations
    vd = scope[2]
    other = VDOM.objects.create(firewall=vd.firewall, name='other')
    with pytest.raises(ValidationError): save_firewall_group(actor=admin, name='Duplicate', vdom_ids=[vd.pk, other.pk])
    group = save_firewall_group(actor=admin, name='Branches', vdom_ids=[vd.pk])
    for cap in ['view','submit']: GroupGrant.objects.create(user=scope[0],firewall_group=group,capability=cap)
    assert resolve_destinations(actor=scope[0], target_kind='firewall_group', firewall_group_id=group.pk) == [vd]
    with pytest.raises(ValidationError): resolve_destinations(actor=scope[0], target_kind='firewall', vdom_id=vd.pk, firewall_group_id=group.pk)
    vd.enabled = False
    vd.save()
    with pytest.raises(PermissionDenied): resolve_destinations(actor=scope[0], target_kind='firewall_group', firewall_group_id=group.pk)


def test_partial_scope_user_cannot_discover_group(admin, scope):
    from apps.firewalls.groups import save_firewall_group, visible_firewall_groups, resolve_destinations
    other = VDOM.objects.create(firewall=Firewall.objects.create(name='Hidden', hostname='192.0.2.2'), name='root')
    group = save_firewall_group(actor=admin, name='Secret group', vdom_ids=[scope[2].pk, other.pk])
    assert not visible_firewall_groups(scope[0]).filter(pk=group.pk).exists()
    with pytest.raises(PermissionDenied): resolve_destinations(actor=scope[0], target_kind='firewall_group', firewall_group_id=group.pk)


def test_mismatched_membership_rejected(admin, scope):
    from apps.firewalls.models import FirewallGroup, FirewallGroupMember
    group = FirewallGroup.objects.create(name='Branches')
    fw = Firewall.objects.create(name='Other', hostname='192.0.2.2')
    member = FirewallGroupMember(group=group, firewall=fw, vdom=scope[2])
    with pytest.raises(ValidationError): member.full_clean()


def test_submit_without_view_does_not_reveal_group(admin, scope):
    from apps.firewalls.groups import save_firewall_group, visible_firewall_groups, resolve_destinations
    from apps.changes.forms import InstallationForm
    other = VDOM.objects.create(firewall=Firewall.objects.create(name='Secret',hostname='192.0.2.2'),name='root')
    GroupGrant.objects.create(user=scope[0],firewall_group=group_for(other),capability='submit')
    group = save_firewall_group(actor=admin,name='Secret group',vdom_ids=[scope[2].pk,other.pk])
    assert not visible_firewall_groups(scope[0],'submit').filter(pk=group.pk).exists()
    assert not InstallationForm(user=scope[0]).fields['firewall_group'].queryset.filter(pk=group.pk).exists()
    with pytest.raises(PermissionDenied): resolve_destinations(actor=scope[0],target_kind='firewall_group',firewall_group_id=group.pk)
