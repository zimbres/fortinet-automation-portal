import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_profile_updates_only_current_user_personal_fields(client, scope):
    user, other, _ = scope
    client.force_login(user)
    grants = list(user.group_grants.values_list('pk', flat=True))
    response = client.post('/profile/', {'action':'profile','username':'updated_operator','first_name':'Portal','last_name':'Member','email':'member@example.test','user_id':other.pk,'is_superuser':'on','is_staff':'on','is_active':'','password':'hacked','external_subject':'changed'})
    assert response.status_code == 302
    user.refresh_from_db(); other.refresh_from_db()
    assert (user.username,user.first_name,user.last_name,user.email) == ('operator','Portal','Member','member@example.test')
    assert not user.is_superuser and not user.is_staff and user.is_active
    assert user.check_password('test-password') and user.external_subject == ''
    assert other.username == 'approver'
    assert list(user.group_grants.values_list('pk',flat=True)) == grants
    assert client.get('/profile/').status_code == 200
    assert b'href="/profile/"' in client.get('/').content
    duplicate=client.post('/profile/', {'action':'profile','username':'approver'})
    assert duplicate.status_code == 200
    user.refresh_from_db(); assert user.username == 'operator'


def test_profile_password_validation_and_session(client, scope):
    user=scope[0];client.force_login(user)
    url='/profile/'
    password='Long-River!47-Maple'
    for old,first,second in [('wrong',password,password),('test-password',password,'different'),('test-password','123','123')]:
        assert client.post(url,{'action':'password','old_password':old,'new_password1':first,'new_password2':second}).status_code == 200
        user.refresh_from_db();assert user.check_password('test-password')
    assert client.post(url,{'action':'password','old_password':'test-password','new_password1':password,'new_password2':password}).status_code == 302
    user.refresh_from_db(); assert user.check_password(password)
    assert client.get('/profile/').status_code == 200
    from apps.audit.models import AuditEvent
    assert AuditEvent.objects.filter(actor=user,event_type='account.password_changed').exists()
    assert password not in str(list(AuditEvent.objects.values('metadata')))


def test_profile_requires_login_and_csrf(client,scope):
    assert client.get('/profile/').status_code == 302
    secure=Client(enforce_csrf_checks=True);secure.force_login(scope[0])
    assert secure.post('/profile/',{'action':'profile','username':'blocked'}).status_code == 403


def test_external_account_cannot_create_local_password(client,scope):
    user=scope[0];user.set_unusable_password();user.save(update_fields=['password'])
    client.force_login(user)
    page=client.get('/profile/')
    assert b'identity provider' in page.content and b'name="old_password"' not in page.content
    assert client.post('/profile/',{'action':'password','old_password':'','new_password1':'Long-River!47-Maple','new_password2':'Long-River!47-Maple'}).status_code == 403
    user.refresh_from_db(); assert not user.has_usable_password()
