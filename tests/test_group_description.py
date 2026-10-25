import pytest
from django.core.exceptions import ValidationError
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def test_group_description_create_edit_display_and_search(client,manager):
    from apps.inventory.models import AddressGroup
    client.force_login(manager)
    assert client.post('/groups/new/',{'name':'web_services','description':'Public web destinations','members':[]}).status_code==302
    group=AddressGroup.objects.get()
    assert group.description=='Public web destinations'
    edit=client.get(f'/groups/{group.entry_id}/edit/')
    assert edit.context['form'].initial['description']==group.description
    assert b'Public web destinations' in client.get('/groups/').content
    assert list(client.get('/groups/',{'q':'WEB DESTINATIONS'}).context['records'])==[group]
    assert client.post(f'/groups/{group.entry_id}/edit/',{'name':'web_services','description':'<script>literal text</script>','members':[],'revision':1}).status_code==302
    html=client.get('/groups/').content
    assert b'&lt;script&gt;literal text&lt;/script&gt;' in html
    assert b'<script>literal text</script>' not in html
    group.entry.refresh_from_db();assert group.entry.revision==2


def test_group_description_limit_and_membership_updates_preserve_it(manager):
    from apps.inventory.catalog import save_address_group
    group=save_address_group(actor=manager,name='documented',member_ids=[],description='Purpose of this group')
    save_address_group(actor=manager,name='documented',member_ids=[],entry_id=group.entry_id,expected_revision=1)
    group.refresh_from_db();assert group.description=='Purpose of this group'
    with pytest.raises(ValidationError):save_address_group(actor=manager,name='too_long',member_ids=[],description='x'*501)
    save_address_group(actor=manager,name='documented',member_ids=[],entry_id=group.entry_id,expected_revision=2,description='')
    group.refresh_from_db();assert group.description==''
