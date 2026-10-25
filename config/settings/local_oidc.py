"""Opt-in saved configuration for local development; never imported by production."""
import json
from django.core.exceptions import ImproperlyConfigured

OIDC_KEYS = (
    'PORTAL_AUTH_MODE', 'OIDC_OP_ISSUER', 'OIDC_RP_CLIENT_ID',
    'OIDC_OP_AUTHORIZATION_ENDPOINT', 'OIDC_OP_TOKEN_ENDPOINT',
    'OIDC_OP_USER_ENDPOINT', 'OIDC_OP_JWKS_ENDPOINT',
)


def load_local_oidc(environ, base_dir):
    if environ.get('PORTAL_AUTH_MODE') == 'local':
        return
    filename = base_dir / '.cache' / 'oidc-test.json'
    if not filename.is_file():
        return
    try:
        data = json.loads(filename.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ImproperlyConfigured('Unable to read .cache/oidc-test.json.') from None
    if not isinstance(data, dict) or any(key in data and not isinstance(data[key], str) for key in OIDC_KEYS):
        raise ImproperlyConfigured('Saved OIDC settings must be a JSON object with string values.')
    for key in OIDC_KEYS:
        if key in data:
            environ.setdefault(key, data[key])
    if environ.get('PORTAL_AUTH_MODE') == 'oidc' and not environ.get('OIDC_RP_CLIENT_SECRET') and not environ.get('OIDC_RP_CLIENT_SECRET_FILE'):
        secret_file = base_dir / '.cache' / 'oidc-test-client-secret'
        if not secret_file.is_file():
            raise ImproperlyConfigured('Missing .cache/oidc-test-client-secret for saved OIDC settings.')
        environ['OIDC_RP_CLIENT_SECRET_FILE'] = str(secret_file)
