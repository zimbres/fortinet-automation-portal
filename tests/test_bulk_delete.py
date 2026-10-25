import pytest
from django.core.exceptions import ValidationError,PermissionDenied
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def objects(manager):
    from apps.inventory.catalog import save_address
    return [save_address(actor=manager,name=f'bulk_{i}',kind='subnet',value=f'192.0.2.{i+1}') for i in range(3)]


def test_bulk_delete_requires_preview_and_confirm(client,manager):
    from apps.inventory.models import AddressObject
    from apps.audit.models import AuditEvent
    rows=objects(manager);client.force_login(manager)
    page=client.get('/objects/');assert b'Select all shown' in page.content
    response=client.post('/objects/delete-selected/',{'selected':[f'{o.entry_id}:1' for o in rows[:2]]})
    assert response.status_code==200 and AddressObject.objects.count()==3
    token=response.context['confirmation']
    assert b'bulk_0' in response.content and b'bulk_1' in response.content
    response=client.post('/objects/delete-selected/',{'confirmation':token})
    assert response.status_code==302 and list(AddressObject.objects.values_list('pk',flat=True))==[rows[2].pk]
    assert AuditEvent.objects.filter(event_type='catalog.deleted').count()==2


@pytest.mark.parametrize('blocked',['membership','stale','missing','group'])
def test_bulk_delete_rolls_back_entire_selection(manager,blocked):
    from apps.inventory.catalog import bulk_delete_addresses,save_address_group,save_address
    from apps.inventory.models import AddressObject
    rows=objects(manager);selections={o.entry_id:1 for o in rows[:2]}
    if blocked=='membership':save_address_group(actor=manager,name='protected',member_ids=[rows[1].pk])
    elif blocked=='stale':save_address(actor=manager,name='bulk_1',kind='subnet',value='192.0.2.99',entry_id=rows[1].entry_id,expected_revision=1)
    elif blocked=='missing':selections[999999]=1
    else:
        group=save_address_group(actor=manager,name='not_an_object',member_ids=[])
        selections[group.entry_id]=1
    with pytest.raises(ValidationError):bulk_delete_addresses(actor=manager,selections=selections)
    assert AddressObject.objects.count()==3


def test_bulk_delete_enforces_permissions_and_confirmation_integrity(client,manager,scope):
    from apps.inventory.catalog import bulk_delete_addresses
    from apps.inventory.models import AddressObject
    rows=objects(manager)
    client.force_login(manager)
    preview=client.post('/objects/delete-selected/',{'selected':[f'{rows[0].entry_id}:1']})
    token=preview.context['confirmation']
    assert client.post('/objects/delete-selected/',{'confirmation':token+'tampered'}).status_code==302
    assert AddressObject.objects.count()==3
    assert client.get('/objects/delete-selected/').status_code==405
    from django.test import Client
    secure=Client(enforce_csrf_checks=True);secure.force_login(manager)
    assert secure.post('/objects/delete-selected/',{'confirmation':token}).status_code==403
    from apps.accounts.models import CatalogGrant
    CatalogGrant.objects.create(user=scope[1],capability='catalog_manage')
    client.force_login(scope[1])
    assert client.post('/objects/delete-selected/',{'confirmation':token}).status_code==403
    assert AddressObject.objects.count()==3
    CatalogGrant.objects.filter(user=scope[1]).delete()
    with pytest.raises(PermissionDenied):bulk_delete_addresses(actor=scope[1],selections={rows[0].entry_id:1})
