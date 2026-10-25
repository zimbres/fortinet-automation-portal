from tests.group_helpers import group_for
import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.test import override_settings
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_scope_denies_foreign_or_inactive_user():
    from apps.firewalls.models import Firewall, VDOM
    from apps.accounts.models import GroupGrant
    from apps.accounts.permissions import require_capability
    fw = Firewall.objects.create(name='Edge', hostname='192.0.2.1')
    one = VDOM.objects.create(firewall=fw, name='one')
    two = VDOM.objects.create(firewall=fw, name='two')
    user = User.objects.create_user('operator')
    GroupGrant.objects.create(user=user, firewall_group=group_for(one), capability='submit')
    require_capability(user, one, 'submit')
    with pytest.raises(PermissionDenied):
        require_capability(user, two, 'submit')
    user.is_active = False
    user.save()
    with pytest.raises(PermissionDenied):
        require_capability(user, one, 'submit')


def test_provisioning_requires_superadministrator():
    from apps.accounts.services import provision_user
    user = User.objects.create_user('operator')
    with pytest.raises(PermissionDenied):
        provision_user(actor=user, username='new', role_names=['Operator'])
    user.is_superuser = True
    user.save()
    created = provision_user(actor=user, username='new', role_names=['Operator'])
    assert created.groups.filter(name='Operator').exists()
    assert not created.has_usable_password()


def test_encryption_rotation_and_missing_key():
    from apps.firewalls.crypto import encrypt_secret, decrypt_secret
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    with override_settings(PORTAL_ENCRYPTION_KEYS=[old]):
        value = encrypt_secret('firewall-secret')
        assert 'firewall-secret' not in value
    with override_settings(PORTAL_ENCRYPTION_KEYS=[new, old]):
        assert decrypt_secret(value) == 'firewall-secret'
        assert decrypt_secret(encrypt_secret('new-secret')) == 'new-secret'
    with override_settings(PORTAL_ENCRYPTION_KEYS=[]):
        with pytest.raises(ImproperlyConfigured):
            encrypt_secret('secret')


def test_saved_credentials_rotate_without_exposing_plaintext(scope,settings):
    from django.core.management import call_command
    from apps.firewalls.forms import FirewallEditForm
    firewall = scope[2].firewall
    previous = firewall.encrypted_token
    assert 'test-secret' not in previous
    assert 'test-secret' not in FirewallEditForm(instance=firewall).as_p()
    settings.PORTAL_ENCRYPTION_KEYS = [Fernet.generate_key().decode(),*settings.PORTAL_ENCRYPTION_KEYS]
    call_command('rotate_credentials')
    firewall.refresh_from_db()
    assert firewall.encrypted_token != previous
    assert firewall.get_token() == 'test-secret'


@override_settings(OIDC_OP_TOKEN_ENDPOINT='https://idp.example/token',
                   OIDC_OP_USER_ENDPOINT='https://idp.example/userinfo',
                   OIDC_RP_CLIENT_ID='test', OIDC_RP_CLIENT_SECRET='test')
def test_oidc_does_not_provision_or_elevate():
    from apps.accounts.oidc import PortalOIDCBackend
    backend = PortalOIDCBackend()
    assert backend.create_user({'sub': 'unknown', 'email': 'x@example.com'}) is None
    user = User.objects.create_user('known', email='known@example.test', external_issuer='https://idp.example', external_subject='bound')
    with override_settings(OIDC_OP_ISSUER='https://idp.example'):
        claims = {'sub':'bound','iss':'https://idp.example','email':'known@example.test','email_verified':True}
        assert list(backend.filter_users_by_claims(claims)) == [user]
        assert not backend.filter_users_by_claims({**claims,'iss':'https://other.example'}).exists()
        backend.update_user(user, {**claims,'is_superuser':True,'groups':['Superadministrator']})
    user.refresh_from_db()
    assert not user.is_superuser


@override_settings(OIDC_OP_ISSUER='https://idp.example', OIDC_RP_CLIENT_ID='portal')
@pytest.mark.parametrize('claims', [
    {'iss':'https://wrong.example','sub':'u','aud':'portal','exp':9999999999},
    {'iss':'https://idp.example','sub':'u','aud':'another-app','exp':9999999999},
    {'iss':'https://idp.example','sub':'u','aud':'portal','exp':1},
    {'iss':'https://idp.example','sub':'u','aud':['portal','other'],'exp':9999999999},
])
def test_oidc_rejects_invalid_token_claims(claims):
    from apps.accounts.oidc import validate_id_claims
    from django.core.exceptions import SuspiciousOperation
    with pytest.raises(SuspiciousOperation): validate_id_claims(claims)
