import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User, CatalogGrant
from apps.inventory.models import AddressObject
from tests.test_address_restrictions import admin, operator, restrict

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('role,superuser,allowed', [
    ('Operator', False, False), ('Viewer', False, False), ('Approver', False, False),
    ('Administrator', False, True), ('Superadministrator', True, True),
])
def test_management_routes_require_privileged_role(client, admin, role, superuser, allowed):
    user = User.objects.create_user('person', is_superuser=superuser)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    CatalogGrant.objects.create(user=user, capability='catalog_manage')
    rule = restrict(admin, 'fqdn', 'domain.com')
    client.force_login(user)
    for path in ['/restrictions/', '/restrictions/new/', '/restrictions/import/',
                 f'/restrictions/{rule.pk}/edit/', f'/restrictions/{rule.pk}/delete/']:
        assert client.get(path).status_code == (200 if allowed else 403)
    assert (b'Restricted addresses' in client.get('/objects/').content) == allowed
    assert (b'Override restricted addresses' in client.get('/objects/new/').content) == allowed
    assert (b'Override restricted addresses' in client.get('/objects/import/').content) == allowed
    if not allowed:
        for path, data in [('/restrictions/new/', {'kind':'fqdn', 'value':'blocked.com'}),
                           ('/restrictions/import/', {'content':'blocked.com'}),
                           (f'/restrictions/{rule.pk}/edit/', {'kind':'fqdn', 'value':'changed.com'}),
                           (f'/restrictions/{rule.pk}/delete/', {})]:
            assert client.post(path, data).status_code == 403


def test_admin_management_crud_search_and_audit(client, admin):
    from apps.inventory.models import AddressRestriction
    from apps.audit.models import AuditEvent
    client.force_login(admin)
    assert client.post('/restrictions/new/', {'kind':'subnet', 'value':'10.1.1.0/8'}).status_code == 302
    rule = AddressRestriction.objects.get()
    assert rule.value == '10.0.0.0/8'
    assert b'10.0.0.0/8' in client.get('/restrictions/?q=10.0').content
    assert b'10.0.0.0/8' not in client.get('/restrictions/?q=other').content
    assert client.post(f'/restrictions/{rule.pk}/edit/', {'kind':'fqdn', 'value':'DOMAIN.COM.'}).status_code == 302
    rule.refresh_from_db()
    assert rule.value == 'domain.com'
    assert client.get(f'/restrictions/{rule.pk}/delete/').status_code == 200
    assert AddressRestriction.objects.exists()
    assert client.post(f'/restrictions/{rule.pk}/delete/').status_code == 302
    assert not AddressRestriction.objects.exists()
    assert set(AuditEvent.objects.filter(event_type__startswith='restriction.').values_list('event_type', flat=True)) == {'restriction.created', 'restriction.updated', 'restriction.deleted'}


def test_admin_without_catalog_grant_can_manage_restrictions(client):
    user = User.objects.create_user('admin-no-catalog')
    user.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    client.force_login(user)
    assert client.post('/restrictions/new/', {'kind':'fqdn', 'value':'domain.com'}).status_code == 302
    assert client.get('/objects/new/').status_code == 403


def test_restriction_import_valid_invalid_duplicates_and_long_domains(client, admin):
    from apps.inventory.models import AddressRestriction
    client.force_login(admin)
    long_domain = 'a' * 60 + '.' + 'b' * 60 + '.example.com'
    response = client.post('/restrictions/import/', {'content':f'10.1.1.0/8\n10.0.0.0/8\nDOMAIN.COM.\n*.domain.com\ninvalid\n{long_domain}'})
    assert response.status_code == 200
    assert response.context['result']['created'] == 4
    assert response.context['result']['duplicates'] == 1
    assert len(response.context['result']['errors']) == 1
    assert AddressRestriction.objects.count() == 4
    upload = SimpleUploadedFile('restrictions.csv', b'name,kind,value\nprotected,fqdn,another.com\n')
    assert client.post('/restrictions/import/', {'file':upload}).context['result']['created'] == 1


def test_restriction_import_limits_are_atomic(admin):
    from apps.inventory.restriction_imports import import_restrictions
    from apps.inventory.models import AddressRestriction
    from django.core.exceptions import ValidationError
    for content in [b'x' * 1048577, b'\n'.join(f'h{i}.com'.encode() for i in range(1001)), b'\xff']:
        with pytest.raises(ValidationError):
            import_restrictions(actor=admin, content=content)
    assert not AddressRestriction.objects.exists()


def test_operator_forged_override_does_not_create(client, admin, operator):
    restrict(admin, 'fqdn', 'domain.com')
    client.force_login(operator)
    response = client.post('/objects/new/', {'name':'blocked', 'kind':'fqdn', 'value':'domain.com', 'override_restrictions':'on'})
    assert response.status_code in (200, 403)
    assert not AddressObject.objects.exists()
    response = client.post('/objects/import/', {'content':'domain.com', 'override_restrictions':'on'})
    assert response.status_code in (200, 403)
    if response.status_code == 200:
        batch = response.context['batch']
        assert not batch.override_restrictions
        result = client.post(f'/objects/import/{batch.pk}/confirm/')
        assert b'refused' in result.content.lower()
    assert not AddressObject.objects.exists()


def test_override_forms_and_mixed_import_result(client, admin):
    from apps.audit.models import AuditEvent
    restrict(admin, 'fqdn', 'domain.com')
    client.force_login(admin)
    assert client.post('/objects/new/', {'name':'override', 'kind':'fqdn', 'value':'domain.com', 'override_restrictions':'on'}).status_code == 302
    assert AuditEvent.objects.filter(event_type='catalog.restriction_overridden').count() == 1
    preview = client.post('/objects/import/', {'content':'site.domain.com\nallowed.org'})
    assert b'site.domain.com' in preview.content and b'refused' in preview.content.lower()
    batch = preview.context['batch']
    result = client.post(f'/objects/import/{batch.pk}/confirm/')
    assert result.status_code == 200
    assert b'1 object stored locally' in result.content
    assert b'site.domain.com' in result.content
    assert AddressObject.objects.count() == 2
    repeated = client.post(f'/objects/import/{batch.pk}/confirm/')
    assert b'site.domain.com' in repeated.content
    assert AddressObject.objects.count() == 2
    batch = client.post('/objects/import/', {'content':'another.domain.com', 'override_restrictions':'on'}).context['batch']
    assert batch.override_restrictions
    assert client.post(f'/objects/import/{batch.pk}/confirm/').status_code == 302
    assert AuditEvent.objects.filter(event_type='catalog.restriction_overridden').count() == 2


def test_restriction_errors_are_escaped_and_unauthenticated_redirects(client, admin):
    assert client.get('/restrictions/').status_code == 302
    client.force_login(admin)
    response = client.post('/restrictions/new/', {'kind':'fqdn', 'value':'<script>alert(1)</script>'})
    assert response.status_code == 200
    assert b'<script>alert' not in response.content
    assert b'&lt;script&gt;' in response.content
