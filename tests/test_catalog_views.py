import pytest
from tests.test_catalog import manager
from tests.test_firewall_groups import admin

pytestmark = pytest.mark.django_db


def test_local_catalog_crud_and_no_approval(client, manager):
    from apps.inventory.models import AddressObject
    from apps.changes.models import ChangeRequest, InstallationRequest
    client.force_login(manager)
    assert client.post('/objects/new/', {'name':'portal_test','kind':'subnet','value':'192.0.2.1'}).status_code == 302
    obj = AddressObject.objects.get()
    assert b'portal_test' in client.get('/objects/').content
    assert client.get(f'/objects/{obj.entry_id}/edit/').status_code == 200
    assert client.post('/groups/new/', {'name':'portal_group','members':[obj.pk]}).status_code == 302
    assert not ChangeRequest.objects.exists() and not InstallationRequest.objects.exists()
    assert client.get('/device-inventory/').status_code == 200


def test_catalog_denies_scope_only_user(client, scope):
    client.force_login(scope[0])
    assert client.get('/objects/').status_code == 403
    assert client.post('/objects/new/', {'name':'x','kind':'subnet','value':'192.0.2.1'}).status_code == 403


def test_import_preview_confirmation(client, manager):
    from apps.inventory.models import CatalogImport, AddressObject
    client.force_login(manager)
    assert client.get('/objects/import/example.csv').status_code == 200
    response = client.post('/objects/import/', {'content':'name,kind,value\nportal_a,subnet,192.0.2.1\n'})
    assert response.status_code == 200
    batch = CatalogImport.objects.get()
    assert not AddressObject.objects.exists()
    assert client.post(f'/objects/import/{batch.pk}/confirm/').status_code == 302
    assert AddressObject.objects.count() == 1


def test_firewall_group_admin_and_csrf(client, admin, scope):
    client.force_login(admin)
    assert client.post('/firewall-groups/new/', {'name':'Branches','vdoms':[scope[2].pk],'enabled':'on'}).status_code == 302
    assert b'Branches' in client.get('/firewall-groups/').content
    from django.test import Client
    secure = Client(enforce_csrf_checks=True)
    secure.force_login(admin)
    assert secure.post('/objects/new/',{}).status_code == 403


def test_dashboard_catalog_counts_require_catalog_access(client, manager, scope):
    from apps.inventory.catalog import save_address
    save_address(actor=manager,name='local_one',kind='subnet',value='192.0.2.1')
    client.force_login(manager)
    assert client.get('/').context['catalog_counts'] == {'objects':1,'groups':0}
    client.force_login(scope[1])
    assert client.get('/').context['catalog_counts'] is None
