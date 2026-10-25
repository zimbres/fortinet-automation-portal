import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from apps.firewalls.models import VDOM,FirewallGroupMember
from tests.group_helpers import group_for

pytestmark=pytest.mark.django_db


def test_remove_vdom_preserves_history_and_hides_active_configuration(client,scope):
    from apps.firewalls.services import remove_vdom
    from apps.inventory.models import InventoryScan
    from apps.audit.models import AuditEvent
    user=scope[0]; user.is_superuser=True; user.save()
    vd=VDOM.objects.create(firewall=scope[2].firewall,name='old-vdom')
    scan=InventoryScan.objects.create(vdom=vd,findings={'old':'unknown'})
    remove_vdom(actor=user,vdom_id=vd.pk)
    vd.refresh_from_db(); assert not vd.enabled and vd.removed_at is not None
    assert InventoryScan.objects.get(pk=scan.pk).vdom_id==vd.pk
    assert AuditEvent.objects.filter(event_type='vdom.removed',metadata__vdom_id=vd.pk).exists()
    client.force_login(user)
    assert b'old-vdom' not in client.get('/firewalls/').content
    page=client.get(f'/vdom/{vd.pk}/delete/'); assert page.status_code==404
    response=client.post(f'/firewalls/{vd.firewall_id}/vdom/',{'name':'old-vdom'})
    assert response.status_code==302
    vd.refresh_from_db(); assert vd.enabled and vd.removed_at is None
    assert VDOM.objects.filter(firewall=vd.firewall,name='old-vdom').count()==1


def test_group_destination_must_be_reassigned_before_removal(scope):
    from apps.firewalls.services import remove_vdom
    from apps.firewalls.groups import save_firewall_group
    user=scope[0]; user.is_superuser=True; user.save()
    vd=scope[2]; group=group_for(vd)
    with pytest.raises(ValidationError,match='group'): remove_vdom(actor=user,vdom_id=vd.pk)
    other=VDOM.objects.create(firewall=vd.firewall,name='replacement')
    save_firewall_group(actor=user,name=group.name,vdom_ids=[other.pk],group_id=group.pk)
    assert FirewallGroupMember.objects.get(group=group,firewall=vd.firewall).vdom==other
    remove_vdom(actor=user,vdom_id=vd.pk)
    assert FirewallGroupMember.objects.filter(group=group,vdom=other).exists()


def test_remove_vdom_requires_superadmin_and_csrf(client,scope):
    from apps.firewalls.services import remove_vdom
    from django.test import Client
    user=scope[0]; vd=VDOM.objects.create(firewall=scope[2].firewall,name='extra')
    with pytest.raises(PermissionDenied): remove_vdom(actor=user,vdom_id=vd.pk)
    client.force_login(user)
    assert client.post(f'/vdom/{vd.pk}/delete/').status_code==403
    user.is_superuser=True; user.save()
    secure=Client(enforce_csrf_checks=True); secure.force_login(user)
    assert secure.post(f'/vdom/{vd.pk}/delete/').status_code==403
    page=client.get(f'/vdom/{vd.pk}/delete/')
    assert page.status_code==200
    vd.refresh_from_db(); assert vd.enabled
    assert client.post(f'/vdom/{vd.pk}/delete/').status_code==302
    vd.refresh_from_db(); assert not vd.enabled


def test_removed_vdom_cannot_be_selected_as_group_destination(scope):
    from apps.firewalls.services import remove_vdom
    from apps.firewalls.groups import save_firewall_group
    user=scope[0]; user.is_superuser=True; user.save()
    vd=VDOM.objects.create(firewall=scope[2].firewall,name='retired')
    remove_vdom(actor=user,vdom_id=vd.pk)
    with pytest.raises(ValidationError,match='enabled'):
        save_firewall_group(actor=user,name='Invalid destination',vdom_ids=[vd.pk])


def test_firewall_membership_rejects_removed_or_foreign_explicit_vdom(scope):
    from apps.firewalls.services import remove_vdom
    from apps.firewalls.groups import set_firewall_groups
    from apps.firewalls.models import Firewall
    user=scope[0]; user.is_superuser=True; user.save()
    vd=VDOM.objects.create(firewall=scope[2].firewall,name='removed')
    remove_vdom(actor=user,vdom_id=vd.pk)
    foreign=VDOM.objects.create(firewall=Firewall.objects.create(name='Foreign',hostname='192.0.2.2'),name='root')
    for destination in (vd,foreign):
        with pytest.raises(ValidationError,match='enabled VDOM'):
            set_firewall_groups(firewall=scope[2].firewall,group_ids=[group_for(scope[2]).pk],vdom=destination)
