import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from unittest.mock import patch

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(scope):
    from django.contrib.auth.models import Group
    scope[0].groups.add(Group.objects.get_or_create(name='Administrator')[0])
    from apps.accounts.models import CatalogGrant
    CatalogGrant.objects.create(user=scope[0], capability='catalog_manage')
    return scope[0]


def test_catalog_requires_explicit_global_grant(scope):
    from apps.inventory.catalog import save_address
    with pytest.raises(PermissionDenied):
        save_address(actor=scope[0], name='a', kind='subnet', value='192.0.2.1')


def test_manage_includes_view_and_superadmin_can_manage(manager):
    from apps.accounts.permissions import require_catalog_capability
    require_catalog_capability(manager, 'catalog_view')
    from apps.accounts.models import User
    admin = User.objects.create_user('admin', is_superuser=True)
    require_catalog_capability(admin, 'catalog_manage')
    admin.is_active = False
    admin.save()
    with pytest.raises(PermissionDenied):
        require_catalog_capability(admin, 'catalog_manage')


def test_local_crud_audited_without_requests_or_http(manager):
    from apps.inventory.catalog import save_address, save_address_group
    from apps.audit.models import AuditEvent
    from apps.changes.models import ChangeRequest
    with patch('apps.fortinet.client.FortinetClient') as remote:
        obj = save_address(actor=manager, name='portal_host', kind='subnet', value='192.0.2.1')
        group = save_address_group(actor=manager, name='portal_group', member_ids=[obj.pk])
        assert list(group.members.values_list('pk', flat=True)) == [obj.pk]
        obj.refresh_from_db()
        assert obj.value == '192.0.2.1/32'
        assert AuditEvent.objects.filter(event_type='catalog.created').count() == 2
        assert ChangeRequest.objects.count() == 0
        remote.assert_not_called()


def test_stale_revision_rejected(manager):
    from apps.inventory.catalog import save_address
    obj = save_address(actor=manager, name='host', kind='fqdn', value='HOST.Example.com.')
    save_address(actor=manager, name='host', kind='fqdn', value='other.example.com', entry_id=obj.entry_id, expected_revision=1)
    with pytest.raises(ValidationError):
        save_address(actor=manager, name='host', kind='fqdn', value='old.example.com', entry_id=obj.entry_id, expected_revision=1)
    obj.refresh_from_db()
    assert obj.value == 'other.example.com'


def test_referenced_object_delete_blocked(manager):
    from apps.inventory.catalog import save_address, save_address_group, delete_catalog_entry
    obj = save_address(actor=manager, name='host', kind='subnet', value='192.0.2.1')
    group = save_address_group(actor=manager, name='group', member_ids=[obj.pk])
    with pytest.raises(ValidationError):
        delete_catalog_entry(actor=manager, entry_id=obj.entry_id, expected_revision=1)
    delete_catalog_entry(actor=manager, entry_id=group.entry_id, expected_revision=1)
    delete_catalog_entry(actor=manager, entry_id=obj.entry_id, expected_revision=1)


def test_shared_namespace_collision_rolls_back(manager):
    from apps.inventory.catalog import save_address, save_address_group
    from apps.inventory.models import CatalogEntry, AddressGroup
    save_address(actor=manager, name='same', kind='subnet', value='192.0.2.1')
    with pytest.raises(ValidationError):
        save_address_group(actor=manager, name='same', member_ids=[])
    assert CatalogEntry.objects.count() == 1
    assert AddressGroup.objects.count() == 0
