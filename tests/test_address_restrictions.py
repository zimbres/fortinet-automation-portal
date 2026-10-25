import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from apps.accounts.models import User, CatalogGrant
from apps.inventory.catalog import save_address

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return User.objects.create_user('restriction-admin', is_superuser=True)


@pytest.fixture
def operator():
    user = User.objects.create_user('restriction-operator')
    CatalogGrant.objects.create(user=user, capability='catalog_manage')
    return user


def restrict(admin, kind, value):
    from apps.inventory.restrictions import save_restriction
    return save_restriction(actor=admin, kind=kind, value=value)


@pytest.mark.parametrize('restricted,submitted', [
    ('10.1.1.0/8', '10.1.1.2/24'), ('10.0.0.0/8', '10.9.8.7'),
    ('10.1.1.2', '10.0.0.0/8'), ('10.0.0.0/8', '0.0.0.0/0'),
])
def test_network_overlap_refused_and_never_saved(admin, operator, restricted, submitted):
    restrict(admin, 'subnet', restricted)
    with pytest.raises(ValidationError, match='restricted'):
        save_address(actor=operator, name='blocked', kind='subnet', value=submitted)
    from apps.inventory.models import AddressObject
    assert not AddressObject.objects.exists()


@pytest.mark.parametrize('rule_kind,rule,value_kind,value,blocked', [
    ('fqdn', 'DOMAIN.COM.', 'fqdn', 'SITE.Domain.com.', True),
    ('fqdn', 'domain.com', 'wildcard_fqdn', '*.domain.com', True),
    ('fqdn', 'site.domain.com', 'wildcard_fqdn', '*.domain.com', True),
    ('fqdn', 'domain.com', 'fqdn', 'domain.com', True),
    ('wildcard_fqdn', '*.domain.com', 'fqdn', 'site.domain.com', True),
    ('wildcard_fqdn', '*.site.domain.com', 'wildcard_fqdn', '*.domain.com', True),
    ('wildcard_fqdn', '*.domain.com', 'fqdn', 'domain.com', False),
    ('fqdn', 'domain.com', 'fqdn', 'otherdomain.com', False),
    ('fqdn', 'domain.com', 'fqdn', 'domain.com.example.org', False),
    ('subnet', '10.0.0.0/8', 'fqdn', 'domain.com', False),
    ('fqdn', 'domain.com', 'subnet', '192.0.2.1', False),
])
def test_domain_boundaries_and_wildcard_overlap(admin, operator, rule_kind, rule, value_kind, value, blocked):
    restrict(admin, rule_kind, rule)
    if blocked:
        with pytest.raises(ValidationError, match='restricted'):
            save_address(actor=operator, name='indicator', kind=value_kind, value=value)
    else:
        assert save_address(actor=operator, name='indicator', kind=value_kind, value=value)


def test_restrictions_normalize_and_deduplicate(admin):
    first = restrict(admin, 'subnet', '10.1.1.0/8')
    assert first.value == '10.0.0.0/8'
    assert restrict(admin, 'subnet', '10.0.0.0/8').pk == first.pk
    assert restrict(admin, 'fqdn', 'DOMAIN.COM.').value == 'domain.com'


@pytest.mark.parametrize('superuser', [True, False])
def test_privileged_override_requires_opt_in_and_is_audited(admin, superuser):
    from apps.audit.models import AuditEvent
    user = User.objects.create_user('privileged', is_superuser=superuser)
    if not superuser:
        user.groups.add(Group.objects.get_or_create(name='Administrator')[0])
        CatalogGrant.objects.create(user=user, capability='catalog_manage')
    rule = restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(ValidationError):
        save_address(actor=user, name='blocked', kind='fqdn', value='site.domain.com')
    obj = save_address(actor=user, name='allowed', kind='fqdn', value='site.domain.com', override_restrictions=True)
    event = AuditEvent.objects.get(event_type='catalog.restriction_overridden')
    assert event.actor_id == user.pk
    assert event.metadata['entry_id'] == obj.entry_id
    assert event.metadata['target_id'] == rule.pk


def test_operator_cannot_manage_or_forge_override(admin, operator):
    from apps.inventory.restrictions import save_restriction
    with pytest.raises(PermissionDenied):
        save_restriction(actor=operator, kind='fqdn', value='domain.com')
    restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(PermissionDenied):
        save_address(actor=operator, name='blocked', kind='fqdn', value='domain.com', override_restrictions=True)


def test_edit_is_checked_without_mutating_old_object(admin, operator):
    obj = save_address(actor=operator, name='host', kind='fqdn', value='allowed.com')
    restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(ValidationError):
        save_address(actor=operator, name='host', kind='fqdn', value='domain.com', entry_id=obj.entry_id, expected_revision=1)
    obj.refresh_from_db()
    assert obj.value == 'allowed.com'
    assert obj.entry.revision == 1


def test_allowed_host_bits_are_normalized(operator):
    assert save_address(actor=operator, name='network', kind='subnet', value='192.0.2.9/24').value == '192.0.2.0/24'


def test_override_audit_rolls_back_on_failed_save(admin):
    from apps.audit.models import AuditEvent
    restrict(admin, 'fqdn', 'domain.com')
    save_address(actor=admin, name='existing', kind='fqdn', value='allowed.com')
    with pytest.raises(ValidationError):
        save_address(actor=admin, name='existing', kind='fqdn', value='domain.com', override_restrictions=True)
    assert not AuditEvent.objects.filter(event_type='catalog.restriction_overridden').exists()


def test_mixed_import_creates_allowed_and_retains_refusals(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import AddressObject
    restrict(admin, 'fqdn', 'domain.com')
    batch = preview_import(actor=operator, content=b'site.domain.com\nallowed.example.org\n*.domain.com')
    assert not batch.errors
    assert len(batch.refused_rows) == 2
    created = confirm_import(actor=operator, token=batch.pk)
    assert [obj.value for obj in created] == ['allowed.example.org']
    batch.refresh_from_db()
    assert {row['value'] for row in batch.refused_rows} == {'site.domain.com', '*.domain.com'}
    assert all('domain.com' in row['reason'] for row in batch.refused_rows)
    assert [obj.pk for obj in confirm_import(actor=operator, token=batch.pk)] == [created[0].pk]
    assert AddressObject.objects.count() == 1


def test_confirmation_rechecks_new_restrictions_and_all_refused(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    batch = preview_import(actor=operator, content=b'site.domain.com')
    assert not batch.refused_rows
    restrict(admin, 'fqdn', 'domain.com')
    assert confirm_import(actor=operator, token=batch.pk) == []
    batch.refresh_from_db()
    assert batch.completed_at and len(batch.refused_rows) == 1
    assert confirm_import(actor=operator, token=batch.pk) == []


def test_confirmation_allows_removed_restrictions(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.restrictions import delete_restriction
    rule = restrict(admin, 'fqdn', 'domain.com')
    batch = preview_import(actor=operator, content=b'domain.com')
    assert len(batch.refused_rows) == 1
    delete_restriction(actor=admin, restriction_id=rule.pk)
    assert len(confirm_import(actor=operator, token=batch.pk)) == 1
    batch.refresh_from_db()
    assert batch.refused_rows == []


def test_import_override_is_bound_and_rechecks_privilege(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import CatalogImport
    restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(PermissionDenied):
        preview_import(actor=operator, content=b'domain.com', override_restrictions=True)
    operator.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    batch = preview_import(actor=operator, content=b'domain.com', override_restrictions=True)
    assert not batch.refused_rows
    operator.groups.clear()
    with pytest.raises(PermissionDenied):
        confirm_import(actor=operator, token=batch.pk)
    batch.refresh_from_db()
    assert batch.completed_at is None
    operator.groups.add(Group.objects.get(name='Administrator'))
    CatalogImport.objects.filter(pk=batch.pk).update(override_restrictions=False)
    with pytest.raises(ValidationError):
        confirm_import(actor=operator, token=batch.pk)


def test_import_with_restrictions_still_rejects_malformed_rows(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    restrict(admin, 'fqdn', 'domain.com')
    batch = preview_import(actor=operator, content=b'domain.com\nallowed.org\n999.1.1.1')
    assert batch.errors
    with pytest.raises(ValidationError):
        confirm_import(actor=operator, token=batch.pk)


@pytest.mark.parametrize('deleted', [False, True])
def test_all_refused_import_still_rejects_stale_group(admin, operator, deleted):
    from apps.inventory.catalog import save_address_group
    from apps.inventory.imports import preview_import, confirm_import
    group = save_address_group(actor=admin, name='destination', member_ids=[])
    batch = preview_import(actor=operator, content=b'domain.com', group_id=group.pk)
    if deleted:
        group.entry.delete()
    else:
        save_address_group(actor=admin, name='destination', member_ids=[], entry_id=group.entry_id, expected_revision=1)
    restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(ValidationError):
        confirm_import(actor=operator, token=batch.pk)
    batch.refresh_from_db()
    assert batch.completed_at is None


def test_new_name_conflict_is_fatal_even_when_row_is_restricted(admin, operator):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import AddressObject
    batch = preview_import(actor=operator, content=b'name,kind,value\nfirst,fqdn,domain.com\nsecond,fqdn,allowed.org')
    save_address(actor=operator, name='first', kind='fqdn', value='different.org')
    restrict(admin, 'fqdn', 'domain.com')
    with pytest.raises(ValidationError):
        confirm_import(actor=operator, token=batch.pk)
    assert list(AddressObject.objects.values_list('entry__name', flat=True)) == ['first']
    batch.refresh_from_db()
    assert batch.completed_at is None


def test_numeric_ip_cannot_bypass_subnet_restriction_as_fqdn(admin, operator):
    restrict(admin, 'subnet', '10.0.0.0/8')
    with pytest.raises(ValidationError):
        save_address(actor=operator, name='disguised-ip', kind='fqdn', value='10.1.1.2')


def test_inactive_and_revoked_admin_cannot_override_or_manage(admin, operator):
    from apps.inventory.restrictions import save_restriction
    operator.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    operator.is_active = False
    operator.save(update_fields=['is_active'])
    with pytest.raises(PermissionDenied):
        save_restriction(actor=operator, kind='fqdn', value='domain.com')
    with pytest.raises(PermissionDenied):
        save_address(actor=operator, name='host', kind='fqdn', value='domain.com', override_restrictions=True)


def test_restriction_import_cannot_exceed_storage_length(admin):
    from apps.inventory.restriction_imports import import_restrictions
    from apps.inventory.models import AddressRestriction
    root = '.'.join(['a' * 63, 'b' * 63, 'c' * 63, 'd' * 61])
    assert len(root) == 253
    result = import_restrictions(actor=admin, content=(root + '\n*.' + root).encode())
    assert result['created'] == 1
    assert len(result['errors']) == 1
    assert list(AddressRestriction.objects.values_list('value', flat=True)) == [root]
