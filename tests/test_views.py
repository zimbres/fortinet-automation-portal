import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_root_requires_login(client):
    assert client.get('/').status_code == 302


def test_dashboard_empty_scope_and_navigation(client, scope):
    client.force_login(scope[0])
    response = client.get('/')
    assert response.status_code == 200
    assert b'Pending approval' in response.content
    assert b'New request' in response.content


def test_foreign_request_is_hidden(client, scope):
    from tests.legacy_helpers import legacy_request
    from apps.accounts.models import User
    item = legacy_request(actor=scope[0],vdom=scope[2],operation='create_address',
        payload={'name':'portal_one','kind':'subnet','value':'192.0.2.1'},idempotency_key='x')
    stranger = User.objects.create_user('stranger')
    client.force_login(stranger)
    assert client.get(f'/requests/{item.pk}/').status_code == 404


def test_mutation_requires_csrf(scope):
    client = Client(enforce_csrf_checks=True)
    client.force_login(scope[0])
    assert client.post('/requests/new/',{}).status_code == 403


def test_health_endpoint(client):
    assert client.get('/health/').json() == {'status':'ok'}


def test_inventory_template_accepts_subnet_without_fqdn():
    from django.template.loader import render_to_string
    html = render_to_string('portal/inventory.html',{'records':[{'name':'host','type':'ipmask','subnet':'192.0.2.1 255.255.255.255'}],'kind':'addresses'})
    assert '192.0.2.1 255.255.255.255' in html


@pytest.mark.parametrize('path',['/firewalls/','/firewalls/new/','/objects/','/groups/','/usage/','/users/','/users/new/','/audit/','/history/','/approvals/','/requests/new/'])
def test_superadministrator_pages_render(client,scope,path):
    user = scope[0]
    user.is_superuser = True
    user.save()
    client.force_login(user)
    response = client.get(path)
    assert response.status_code == 200
    assert b'test-secret' not in response.content
