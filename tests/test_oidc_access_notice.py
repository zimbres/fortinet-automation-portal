import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from apps.accounts.oidc import PortalOIDCBackend

NOTICE = 'Your SSO account does not have access to this portal. Contact your superadministrator to request access.'


@pytest.mark.django_db
@pytest.mark.parametrize('inactive', [False, True])
def test_verified_identity_without_access_gets_notice(settings, monkeypatch, inactive):
    from apps.accounts.models import User
    settings.OIDC_OP_TOKEN_ENDPOINT='https://idp.example/token'
    settings.OIDC_OP_USER_ENDPOINT='https://idp.example/userinfo'
    settings.OIDC_RP_CLIENT_ID='portal'
    settings.OIDC_RP_CLIENT_SECRET='unused'
    settings.OIDC_OP_ISSUER='https://idp.example'
    if inactive:
        User.objects.create_user(username='person@example.com',email='person@example.com',is_active=False)
    backend=PortalOIDCBackend()
    request=RequestFactory().get('/oidc/callback/')
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages=FallbackStorage(request)
    backend.request=request
    monkeypatch.setattr(backend,'get_userinfo',lambda *args: {'iss':'https://idp.example','sub':'subject','email':'person@example.com','email_verified':True})
    assert backend.get_or_create_user('unused','unused',{}) is None
    from apps.accounts.oidc_views import PortalOIDCCallbackView
    view=PortalOIDCCallbackView()
    view.request=request
    response=view.login_failure()
    assert response.url == '/login/'
    assert [str(m) for m in get_messages(request)] == [NOTICE]


def test_unverified_failure_shows_only_generic_notice():
    from apps.accounts.oidc_views import PortalOIDCCallbackView
    request=RequestFactory().get('/oidc/callback/?error=access_denied')
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages=FallbackStorage(request)
    view=PortalOIDCCallbackView()
    view.request=request
    assert view.login_failure().url == '/login/'
    assert NOTICE not in [str(m) for m in get_messages(request)]


@pytest.mark.django_db
def test_unverified_claims_do_not_reveal_account_status(settings):
    settings.OIDC_OP_TOKEN_ENDPOINT='https://idp.example/token'
    settings.OIDC_OP_USER_ENDPOINT='https://idp.example/userinfo'
    settings.OIDC_RP_CLIENT_ID='portal'
    settings.OIDC_RP_CLIENT_SECRET='unused'
    settings.OIDC_OP_ISSUER='https://idp.example'
    backend=PortalOIDCBackend()
    request=RequestFactory().get('/oidc/callback/?account_missing=1')
    backend.request=request
    assert not backend.filter_users_by_claims({'iss':'https://idp.example','sub':'subject','email':'person@example.com','email_verified':False}).exists()
    assert not getattr(request,'_portal_sso_access_denied',False)
