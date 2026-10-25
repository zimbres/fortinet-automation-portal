import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from apps.accounts.models import User, CatalogGrant
from apps.inventory.catalog import save_address_group
from apps.inventory.models import AddressGroup

pytestmark=pytest.mark.django_db


@pytest.mark.parametrize('role,superuser,allowed', [('Operator',False,False),('Approver',False,False),('Viewer',False,False),('Administrator',False,True),('Superadministrator',True,True)])
def test_group_creation_requires_admin_role(client,role,superuser,allowed):
    user=User.objects.create_user(username='person@example.com',email='person@example.com',is_superuser=superuser)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    CatalogGrant.objects.create(user=user,capability='catalog_manage')
    client.force_login(user)
    listing=client.get('/groups/')
    assert (b'Create address group' in listing.content) == allowed
    assert client.get('/groups/new/').status_code == (200 if allowed else 403)
    if allowed:
        save_address_group(actor=user,name='new_group',member_ids=[])
    else:
        assert client.post('/groups/new/',{'name':'new_group','members':[]}).status_code == 403
        with pytest.raises(PermissionDenied):
            save_address_group(actor=user,name='new_group',member_ids=[])
        assert not AddressGroup.objects.exists()


def test_administrator_still_requires_catalog_manage():
    user=User.objects.create_user(username='admin@example.com')
    user.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    with pytest.raises(PermissionDenied):
        save_address_group(actor=user,name='blocked',member_ids=[])


def test_operator_can_add_objects_to_existing_group():
    from apps.inventory.catalog import save_address
    admin=User.objects.create_user(username='super@example.com',is_superuser=True)
    group=save_address_group(actor=admin,name='existing',member_ids=[])
    operator=User.objects.create_user(username='operator@example.com')
    operator.groups.add(Group.objects.get_or_create(name='Operator')[0])
    CatalogGrant.objects.create(user=operator,capability='catalog_manage')
    obj=save_address(actor=operator,name='indicator',kind='subnet',value='192.0.2.1',group_id=group.pk)
    assert group.members.filter(pk=obj.pk).exists()
