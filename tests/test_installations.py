from tests.group_helpers import group_for
import pytest
from django.core.exceptions import ValidationError, PermissionDenied
from tests.test_catalog import manager
from tests.test_firewall_groups import admin

pytestmark = pytest.mark.django_db


@pytest.fixture
def installation(scope, manager):
    from apps.inventory.catalog import save_address, save_address_group
    from apps.changes.installations import submit_installation
    obj = save_address(actor=manager, name='portal_host', kind='subnet', value='192.0.2.1')
    group = save_address_group(actor=manager, name='portal_group', member_ids=[obj.pk])
    item = submit_installation(actor=manager, object_ids=[obj.pk], group_ids=[group.pk], target_kind='firewall_group', firewall_group_id=group_for(scope[2]).pk, idempotency_key='install')
    return item, obj, group


def test_dependencies_snapshot_and_catalog_edits(installation, manager):
    from apps.inventory.catalog import save_address, delete_catalog_entry
    from apps.changes.installations import check_installation_authorization
    item, obj, group = installation
    assert len(item.snapshot['objects']) == 1
    assert item.snapshot['groups'][0]['members'] == ['portal_host']
    save_address(actor=manager, entry_id=obj.entry_id, expected_revision=1, name='portal_host', kind='subnet', value='192.0.2.2')
    item.refresh_from_db()
    assert item.snapshot['objects'][0]['value'] == '192.0.2.1/32'
    delete_catalog_entry(actor=manager, entry_id=group.entry_id, expected_revision=1)
    delete_catalog_entry(actor=manager, entry_id=obj.entry_id, expected_revision=2)
    assert item.snapshot['objects'][0]['name'] == 'portal_host'
    item.snapshot = {}
    with pytest.raises(ValidationError): item.save()


def test_independent_approval_and_revoked_access(installation, scope):
    from apps.changes.installations import decide_installation, check_installation_authorization
    from apps.accounts.models import GroupGrant
    item = installation[0]
    with pytest.raises(PermissionDenied): decide_installation(actor=scope[0], request_id=item.pk, status='APPROVED')
    decide_installation(actor=scope[1], request_id=item.pk, status='APPROVED')
    target = item.targets.get()
    check_installation_authorization(target)
    GroupGrant.objects.filter(user=scope[0], capability='submit').delete()
    with pytest.raises(PermissionDenied): check_installation_authorization(target)
    with pytest.raises(ValidationError): decide_installation(actor=scope[1], request_id=item.pk, status='REJECTED')


def test_idempotency_and_empty_selection(installation, scope, manager):
    from apps.changes.installations import submit_installation
    item, obj, group = installation
    data = dict(actor=manager, object_ids=[obj.pk], group_ids=[group.pk], target_kind='firewall_group', firewall_group_id=group_for(scope[2]).pk, idempotency_key='install')
    assert submit_installation(**data).pk == item.pk
    data['group_ids'] = []
    with pytest.raises(ValidationError): submit_installation(**data)
    data.update(object_ids=[], idempotency_key='empty')
    with pytest.raises(ValidationError): submit_installation(**data)


def test_group_targets_frozen_and_all_target_permissions(installation, scope, manager, admin):
    from apps.accounts.models import GroupGrant
    from apps.firewalls.models import Firewall, VDOM
    from apps.firewalls.groups import save_firewall_group
    from apps.changes.installations import submit_installation, decide_installation, installations_for
    other = VDOM.objects.create(firewall=Firewall.objects.create(name='Second', hostname='192.0.2.2'), name='root')
    GroupGrant.objects.create(user=manager, firewall_group=group_for(other), capability='submit')
    GroupGrant.objects.create(user=manager, firewall_group=group_for(other), capability='view')
    group = save_firewall_group(actor=admin, name='Branches', vdom_ids=[scope[2].pk, other.pk])
    for cap in ['view','submit']: GroupGrant.objects.create(user=manager,firewall_group=group,capability=cap)
    item = submit_installation(actor=manager, object_ids=[installation[1].pk], group_ids=[], target_kind='firewall_group', firewall_group_id=group.pk, idempotency_key='multi')
    save_firewall_group(actor=admin, name='Branches', vdom_ids=[scope[2].pk], group_id=group.pk)
    assert item.targets.count() == 2
    assert not installations_for(scope[1]).filter(pk=item.pk).exists()
    with pytest.raises(PermissionDenied): decide_installation(actor=scope[1], request_id=item.pk, status='APPROVED')


def test_snapshot_assembly_never_mixes_revisions(installation, manager, scope, monkeypatch):
    from apps.changes import installations
    from apps.inventory.models import CatalogEntry
    before = installations.InstallationRequest.objects.count()
    original = installations.build_snapshot
    def changed(**kwargs):
        result = original(**kwargs)
        CatalogEntry.objects.filter(pk=installation[1].entry_id).update(revision=99)
        return result
    monkeypatch.setattr(installations, 'build_snapshot', changed)
    with pytest.raises(ValidationError):
        installations.submit_installation(actor=manager, object_ids=[installation[1].pk], group_ids=[], target_kind='firewall_group', firewall_group_id=group_for(scope[2]).pk, idempotency_key='race')
    assert installations.InstallationRequest.objects.count() == before


def test_approve_without_view_does_not_reveal_queue(installation, scope):
    from apps.accounts.models import GroupGrant
    from apps.changes.installations import installations_for, decide_installation
    GroupGrant.objects.filter(user=scope[1],capability='view').delete()
    assert not installations_for(scope[1],'approve').exists()
    with pytest.raises(PermissionDenied): decide_installation(actor=scope[1],request_id=installation[0].pk,status='APPROVED')
