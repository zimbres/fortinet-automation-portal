"""Production configuration fails closed when required settings are absent."""
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F403

SECRET_KEY = secret_value('DJANGO_SECRET_KEY')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must contain at least 50 characters.')
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Configure explicit DJANGO_ALLOWED_HOSTS.')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
if os.environ.get('PORTAL_AUTH_MODE') not in ('local','oidc'):
    raise ImproperlyConfigured('Set PORTAL_AUTH_MODE explicitly to local or oidc.')
if not PORTAL_ENCRYPTION_KEYS:
    raise ImproperlyConfigured('Production requires PORTAL_ENCRYPTION_KEYS_FILE.')
if os.environ.get('PORTAL_AUTH_MODE') == 'oidc':
    if any(not value.startswith('https://') for value in [OIDC_OP_ISSUER,OIDC_OP_AUTHORIZATION_ENDPOINT,
           OIDC_OP_TOKEN_ENDPOINT,OIDC_OP_USER_ENDPOINT,OIDC_OP_JWKS_ENDPOINT]):
        raise ImproperlyConfigured('Production identity provider endpoints must use HTTPS.')
