import pytest
from django.core.exceptions import ValidationError
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def existing_group(manager):
    from apps.inventory.catalog import save_address,save_address_group
    obj=save_address(actor=manager,name='existing',kind='subnet',value='192.0.2.1')
    return save_address_group(actor=manager,name='chosen_group',member_ids=[obj.pk]),obj


def test_create_object_adds_to_selected_group_without_replacing_members(client,manager):
    from apps.inventory.models import AddressObject
    group,old=existing_group(manager)
    client.force_login(manager)
    response=client.post('/objects/new/',{'name':'new_host','kind':'subnet','value':'192.0.2.2','group':group.pk})
    assert response.status_code==302
    new=AddressObject.objects.get(entry__name='new_host')
    assert set(group.members.values_list('pk',flat=True))=={old.pk,new.pk}
    group.entry.refresh_from_db();assert group.entry.revision==2


def test_invalid_group_rolls_back_object_creation(manager):
    from apps.inventory.catalog import save_address
    from apps.inventory.models import AddressObject
    with pytest.raises(ValidationError):
        save_address(actor=manager,name='not_created',kind='subnet',value='192.0.2.2',group_id=999999)
    assert not AddressObject.objects.exists()


def test_import_group_is_previewed_and_confirmed_once(client,manager):
    from apps.inventory.models import CatalogImport,AddressObject
    group,old=existing_group(manager)
    client.force_login(manager)
    page=client.post('/objects/import/',{'content':'192.0.2.2\nnew.example.test','group':group.pk})
    assert page.status_code==200 and b'Add new objects to' in page.content
    batch=CatalogImport.objects.get()
    assert batch.group_snapshot['id']==group.pk
    assert AddressObject.objects.count()==1
    assert client.post(f'/objects/import/{batch.pk}/confirm/',{'group':999999}).status_code==302
    assert group.members.count()==3
    group.entry.refresh_from_db();assert group.entry.revision==2
    assert client.post(f'/objects/import/{batch.pk}/confirm/').status_code==302
    group.entry.refresh_from_db();assert group.entry.revision==2 and group.members.count()==3


@pytest.mark.parametrize('change',['modify','delete','tamper'])
def test_group_change_or_deleted_preview_rejects_import_atomically(manager,change):
    from apps.inventory.catalog import save_address_group,delete_catalog_entry
    from apps.inventory.imports import preview_import,confirm_import
    from apps.inventory.models import AddressObject,CatalogImport
    group,old=existing_group(manager)
    batch=preview_import(actor=manager,content=b'192.0.2.2',group_id=group.pk)
    if change=='modify':save_address_group(actor=manager,name='renamed_group',member_ids=[old.pk],entry_id=group.entry_id,expected_revision=1)
    elif change=='delete':delete_catalog_entry(actor=manager,entry_id=group.entry_id,expected_revision=1)
    else:CatalogImport.objects.filter(pk=batch.pk).update(group_snapshot=None)
    with pytest.raises(ValidationError):confirm_import(actor=manager,token=batch.pk)
    assert AddressObject.objects.count()==1
    batch.refresh_from_db();assert batch.completed_at is None
