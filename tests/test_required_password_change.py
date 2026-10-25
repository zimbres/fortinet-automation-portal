import pytest
from tests.test_firewall_groups import admin
from apps.accounts.models import User

pytestmark=pytest.mark.django_db


def test_registration_has_no_manual_oidc_identity_and_can_require_change(client,admin):
    client.force_login(admin)
    form=client.get('/users/new/').context['form']
    assert 'external_issuer' not in form.fields and 'external_subject' not in form.fields
    response=client.post('/users/new/',{'username':'new@example.test','role_names':['Viewer'],'password':'Initial-Long!47-Maple','require_password_change':'on','external_issuer':'https://forged.example','external_subject':'forged'})
    assert response.status_code==302
    user=User.objects.get(email='new@example.test')
    assert user.require_password_change
    assert not user.external_issuer and not user.external_subject
    assert client.post('/users/new/',{'username':'no-password@example.test','role_names':['Viewer'],'require_password_change':'on'}).status_code==200
    assert not User.objects.filter(email='no-password@example.test').exists()


def test_required_password_blocks_all_work_until_changed(client,scope):
    user=scope[0];user.email='operator@example.test';user.require_password_change=True;user.save()
    response=client.post('/login/',{'username':user.email,'password':'test-password'})
    assert response.status_code==302 and response.url=='/password/change-required/'
    for url in ['/','/profile/','/objects/','/approvals/','/admin/']:
        response=client.get(url)
        assert response.status_code==302 and response.url=='/password/change-required/'
    assert client.post('/profile/',{'action':'profile','email':'forged@example.test'}).status_code==302
    user.refresh_from_db();assert user.email=='operator@example.test'
    assert client.get('/password/change-required/').status_code==200
    for old,new,repeat in [('wrong','Different!47-Maple','Different!47-Maple'),('test-password','123','123'),('test-password','test-password','test-password')]:
        assert client.post('/password/change-required/',{'old_password':old,'new_password1':new,'new_password2':repeat}).status_code==200
        user.refresh_from_db();assert user.require_password_change
    response=client.post('/password/change-required/',{'old_password':'test-password','new_password1':'Different!47-Maple','new_password2':'Different!47-Maple'})
    assert response.status_code==302
    user.refresh_from_db();assert not user.require_password_change and user.check_password('Different!47-Maple')
    assert client.get('/').status_code==200


def test_existing_session_is_gated_and_logout_allowed(client,scope):
    user=scope[0];client.force_login(user)
    User.objects.filter(pk=user.pk).update(require_password_change=True)
    assert client.get('/').status_code==302
    assert client.post('/logout/').status_code==302


def test_oidc_user_cannot_be_marked_for_local_password_change(client,admin,scope):
    from apps.accounts.services import update_user
    from django.core.exceptions import ValidationError
    user=scope[0];user.external_issuer='https://idp.example';user.external_subject='subject';user.email='oidc@example.test';user.save()
    client.force_login(admin)
    form=client.get(f'/users/{user.pk}/edit/').context['form']
    assert form.fields['require_password_change'].disabled
    with pytest.raises(ValidationError):
        update_user(actor=admin,user_id=user.pk,username=user.username,email=user.email,role_names=['Viewer'],group_grants={},catalog_access='',require_password_change=True)



def test_admin_can_require_change_for_existing_local_password(client,admin,scope):
    user=scope[0];user.email='operator@example.test';user.save(update_fields=['email'])
    original=user.password;client.force_login(admin)
    response=client.post(f'/users/{user.pk}/edit/',{'username':user.email,'role_names':['Viewer'],'is_active':'on','require_password_change':'on'})
    assert response.status_code==302
    user.refresh_from_db();assert user.require_password_change and user.password==original
    assert client.get(f'/users/{user.pk}/edit/').context['form'].initial['require_password_change']


def test_required_password_change_requires_csrf(scope):
    from django.test import Client
    user=scope[0];user.require_password_change=True;user.save(update_fields=['require_password_change'])
    client=Client(enforce_csrf_checks=True);client.force_login(user)
    assert client.post('/password/change-required/',{'old_password':'test-password','new_password1':'Different!47-Maple','new_password2':'Different!47-Maple'}).status_code==403
    user.refresh_from_db();assert user.require_password_change and user.check_password('test-password')
