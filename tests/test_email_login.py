import pytest
from django.contrib.auth import authenticate
from django.test import override_settings
from apps.accounts.models import User

pytestmark=pytest.mark.django_db


def test_local_auth_uses_email_not_username(client,scope):
    user=scope[0];user.email='operator@example.test';user.save(update_fields=['email'])
    with override_settings(AUTHENTICATION_BACKENDS=['apps.accounts.backends.EmailBackend']):
        assert authenticate(username='OPERATOR@example.test',password='test-password')==user
        assert authenticate(username='operator',password='test-password') is None
        assert authenticate(username=user.email,password='wrong') is None
        assert client.post('/login/',{'username':user.email,'password':'test-password'}).status_code==302
        user.is_active=False;user.save(update_fields=['is_active'])
        assert authenticate(username=user.email,password='test-password') is None


@override_settings(OIDC_OP_ISSUER='https://idp.example',OIDC_RP_CLIENT_ID='test',OIDC_RP_CLIENT_SECRET='test',OIDC_OP_TOKEN_ENDPOINT='https://idp.example/token',OIDC_OP_USER_ENDPOINT='https://idp.example/userinfo')
def test_oidc_links_by_verified_email_and_preserves_permissions(scope):
    from apps.accounts.oidc import PortalOIDCBackend
    user=scope[0];user.email='operator@example.test';user.save(update_fields=['email'])
    backend=PortalOIDCBackend()
    claims={'iss':'https://idp.example','sub':'subject-123','email':'OPERATOR@example.test','email_verified':True,'given_name':'Provider','family_name':'Member'}
    assert list(backend.filter_users_by_claims(claims))==[user]
    user=backend.update_user(user,claims)
    assert user.external_subject=='subject-123' and user.external_issuer==claims['iss']
    assert user.first_name=='Provider' and user.last_name=='Member'
    assert not user.is_superuser and user.group_grants.count()==2
    assert not backend.filter_users_by_claims({**claims,'email_verified':False}).exists()
    assert not backend.filter_users_by_claims({k:v for k,v in claims.items() if k!='email_verified'}).exists()
    assert not backend.filter_users_by_claims({**claims,'sub':'another-subject'}).exists()
    assert not backend.filter_users_by_claims({**claims,'email':'unknown@example.test'}).exists()


def test_oidc_profile_cannot_be_changed_even_by_post(client,scope):
    user=scope[0];user.email='operator@example.test';user.external_issuer='https://idp.example';user.external_subject='subject';user.save()
    client.force_login(user)
    page=client.get('/profile/')
    assert b'identity provider' in page.content and b'Save profile' not in page.content
    assert b'name="old_password"' not in page.content
    assert client.post('/profile/',{'action':'profile','email':'attacker@example.test','first_name':'Changed'}).status_code==403
    assert client.post('/profile/',{'action':'password','old_password':'test-password','new_password1':'Long-River!47-Maple','new_password2':'Long-River!47-Maple'}).status_code==403
    user.refresh_from_db();assert user.email=='operator@example.test' and user.first_name==''


def test_email_collision_rejected_case_insensitively(client,scope):
    from django.db import IntegrityError,transaction
    user=scope[0];user.email='operator@example.test';user.save(update_fields=['email'])
    with pytest.raises(IntegrityError),transaction.atomic():
        User.objects.create_user('duplicate',email='OPERATOR@example.test')
    client.force_login(scope[1])
    response=client.post('/profile/',{'action':'profile','email':'OPERATOR@example.test'})
    assert response.status_code==200
    scope[1].refresh_from_db();assert scope[1].email!='OPERATOR@example.test'
