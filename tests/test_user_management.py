from tests.group_helpers import group_for
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from apps.accounts.models import User, GroupGrant, CatalogGrant
from tests.test_firewall_groups import admin

pytestmark=pytest.mark.django_db


def test_superadmin_can_edit_user_and_exact_grants(admin,scope):
    from apps.accounts.services import update_user
    user=scope[0]
    old_password=user.password
    updated=update_user(actor=admin,user_id=user.pk,username='renamed',email='new@example.com',role_names=['Approver'],group_grants={'view':[group_for(scope[2]).pk],'approve':[group_for(scope[2]).pk]},catalog_access='catalog_view',password='',is_active=True)
    assert updated.username=='renamed' and updated.email=='new@example.com'
    assert updated.password==old_password
    assert set(updated.groups.values_list('name',flat=True))=={'Approver'}
    assert set(updated.group_grants.values_list('capability',flat=True))=={'view','approve'}
    assert CatalogGrant.objects.filter(user=updated,capability='catalog_view').exists()


def test_edit_user_requires_superadmin_and_protects_current_admin(admin,scope):
    from apps.accounts.services import update_user
    data=dict(user_id=admin.pk,username='admin',email='',role_names=['Viewer'],group_grants={},catalog_access='',password='',is_active=True)
    with pytest.raises(PermissionDenied): update_user(actor=scope[0],**data)
    with pytest.raises(ValidationError): update_user(actor=admin,**data)
    admin.refresh_from_db()
    assert admin.is_superuser and admin.is_active


def test_invalid_user_edit_is_atomic(admin,scope):
    from apps.accounts.services import update_user
    before=set(scope[0].group_grants.values_list('capability',flat=True))
    with pytest.raises(ValidationError):
        update_user(actor=admin,user_id=scope[0].pk,username=scope[1].username,email='',role_names=['Viewer'],group_grants={},catalog_access='',password='',is_active=False)
    scope[0].refresh_from_db()
    assert scope[0].is_active
    assert set(scope[0].group_grants.values_list('capability',flat=True))==before


def test_edit_user_page_and_scope_preservation(client,admin,scope):
    client.force_login(admin)
    page=client.get(f'/users/{scope[0].pk}/edit/')
    assert page.status_code==200
    assert set(page.context['form'].initial['submit_firewall_groups'])=={group_for(scope[2]).pk}
    response=client.post(f'/users/{scope[0].pk}/edit/',{'username':'edited@example.test','email':'','role_names':['Operator'],'view_firewall_groups':[group_for(scope[2]).pk],'submit_firewall_groups':[group_for(scope[2]).pk],'catalog_access':'catalog_manage','is_active':'on','password':''})
    assert response.status_code==302
    scope[0].refresh_from_db()
    assert scope[0].username=='edited@example.test'
    assert scope[0].group_grants.filter(capability='submit',firewall_group=group_for(scope[2])).exists()
    client.force_login(scope[1])
    assert client.get(f'/users/{scope[0].pk}/edit/').status_code==403


def test_delete_user_deactivates_and_preserves_history(client,admin,scope):
    from tests.legacy_helpers import legacy_request
    item=legacy_request(actor=scope[0],vdom=scope[2],operation='create_address',payload={'name':'portal_history','kind':'subnet','value':'192.0.2.1'},idempotency_key='user-delete')
    client.force_login(admin)
    assert client.get(f'/users/{scope[0].pk}/delete/').status_code==200
    scope[0].refresh_from_db()
    assert scope[0].is_active
    assert client.post(f'/users/{scope[0].pk}/delete/').status_code==302
    scope[0].refresh_from_db(); item.refresh_from_db()
    assert not scope[0].is_active and item.requester_id==scope[0].pk
    assert scope[0].pk not in [u.pk for u in client.get('/users/').context['users']]
    assert scope[0].pk in [u.pk for u in client.get('/users/?inactive=1').context['users']]
    from apps.accounts.permissions import require_capability
    with pytest.raises(PermissionDenied): require_capability(scope[0],scope[2],'submit')


def test_delete_protects_current_admin_and_requires_csrf(client,admin):
    client.force_login(admin)
    response=client.post(f'/users/{admin.pk}/delete/')
    assert response.status_code==200
    admin.refresh_from_db()
    assert admin.is_active
    from django.test import Client
    secure=Client(enforce_csrf_checks=True); secure.force_login(admin)
    assert secure.post(f'/users/{admin.pk}/delete/').status_code==403


def test_superadmin_oidc_edit_keeps_identity_readonly_but_updates_access(client,admin,scope):
    user=scope[0]
    user.email='oidc@example.test';user.external_issuer='https://idp.example';user.external_subject='fixed-subject';user.save()
    original_password=user.password
    client.force_login(admin)
    page=client.get(f'/users/{user.pk}/edit/')
    assert 'external_issuer' not in page.context['form'].fields
    assert 'external_subject' not in page.context['form'].fields
    for name in ['username','password']:
        assert page.context['form'].fields[name].disabled
    assert not page.context['form'].fields['role_names'].disabled
    group=group_for(scope[2])
    response=client.post(f'/users/{user.pk}/edit/',{'username':'forged@example.test','external_issuer':'https://attacker.example','external_subject':'replacement','password':'forged-password','role_names':['Administrator'],'view_firewall_groups':[group.pk],'administer_firewall_groups':[group.pk],'is_active':'on','catalog_access':'catalog_view'})
    assert response.status_code==302
    user.refresh_from_db()
    assert (user.username,user.email,user.external_issuer,user.external_subject,user.password)==('operator','oidc@example.test','https://idp.example','fixed-subject',original_password)
    assert user.group_grants.filter(firewall_group=group,capability='administer').exists()
    assert user.groups.filter(name='Administrator').exists()


def test_oidc_identity_is_protected_in_update_service(admin,scope):
    from apps.accounts.services import update_user
    user=scope[0];user.email='oidc@example.test';user.external_issuer='https://idp.example';user.external_subject='fixed-subject';user.save()
    data=dict(actor=admin,user_id=user.pk,username='forged',email='forged@example.test',role_names=['Viewer'],group_grants={},catalog_access='',external_issuer='',external_subject='',is_active=True)
    update_user(**data)
    user.refresh_from_db()
    assert (user.username,user.email,user.external_issuer,user.external_subject)==('operator','oidc@example.test','https://idp.example','fixed-subject')
    with pytest.raises(ValidationError):update_user(**data,password='Long-River!47-Maple')


def test_registration_uses_same_explicit_permission_fields_as_edit(client,admin,scope):
    from apps.firewalls.models import FirewallGroup
    first=group_for(scope[2]);second=FirewallGroup.objects.create(name='Second group')
    client.force_login(admin)
    form=client.get('/users/new/').context['form']
    assert 'firewall_groups' not in form.fields
    for cap in ['view','submit','approve','administer']:
        assert f'{cap}_firewall_groups' in form.fields
    response=client.post('/users/new/',{'username':'new@example.test','role_names':['Administrator'],'view_firewall_groups':[first.pk],'submit_firewall_groups':[second.pk],'approve_firewall_groups':[first.pk],'administer_firewall_groups':[second.pk]})
    assert response.status_code==302
    user=User.objects.get(email='new@example.test')
    assert set(user.group_grants.values_list('firewall_group_id','capability'))=={(first.pk,'view'),(second.pk,'submit'),(first.pk,'approve'),(second.pk,'administer')}
    edit=client.get(f'/users/{user.pk}/edit/').context['form']
    assert edit.initial['submit_firewall_groups']==[second.pk]


def test_registration_role_does_not_implicitly_grant_group_access(client,admin,scope):
    client.force_login(admin)
    response=client.post('/users/new/',{'username':'no-access@example.test','role_names':['Administrator'],'firewall_groups':[group_for(scope[2]).pk]})
    assert response.status_code==302
    user=User.objects.get(email='no-access@example.test')
    assert not user.group_grants.exists()
    response=client.post('/users/new/',{'username':'invalid@example.test','role_names':['Viewer'],'view_firewall_groups':[999999]})
    assert response.status_code==200
    assert not User.objects.filter(email='invalid@example.test').exists()
