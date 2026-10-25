"""Shared settings; production secrets never have development fallbacks."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]


def secret_value(name, *, default=None):
    filename = os.environ.get(f'{name}_FILE')
    if filename:
        return Path(filename).read_text(encoding='utf-8').strip()
    value = os.environ.get(name, default)
    if not value:
        raise ImproperlyConfigured(f'{name} or {name}_FILE must be configured.')
    return value


# Small bounded tolerance for IdP/app clock differences; expiration remains strict.
try:
    OIDC_CLOCK_SKEW_SECONDS = int(os.environ.get('OIDC_CLOCK_SKEW_SECONDS', '60'))
except ValueError as exc:
    raise ImproperlyConfigured('OIDC_CLOCK_SKEW_SECONDS must be an integer.') from exc
if not 0 <= OIDC_CLOCK_SKEW_SECONDS <= 120:
    raise ImproperlyConfigured('OIDC_CLOCK_SKEW_SECONDS must be between 0 and 120.')

DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'apps.accounts.apps.AccountsConfig', 'apps.audit.apps.AuditConfig',
    'apps.firewalls.apps.FirewallsConfig',
    'apps.changes.apps.ChangesConfig',
    'apps.inventory.apps.InventoryConfig',
    'apps.portal.apps.PortalConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.RequiredPasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'apps.portal.context.portal_context',
    ]},
}]
DATA_DIR = Path(os.environ.get('PORTAL_DATA_DIR', BASE_DIR / 'data'))
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'portal.sqlite3',
    'OPTIONS': {'timeout': 20},
}}
AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
MEDIA_ROOT = DATA_DIR / 'media'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
STATICFILES_DIRS = [BASE_DIR / 'static']
PORTAL_ENCRYPTION_KEYS = []
LOGGING = {
    'version':1, 'disable_existing_loggers':False,
    'formatters':{'json':{'()':'apps.audit.logging.JsonFormatter'}},
    'handlers':{'audit_console':{'class':'logging.StreamHandler','formatter':'json','stream':'ext://sys.stdout'}},
    'loggers':{'portal.audit':{'handlers':['audit_console'],'level':'INFO','propagate':False}},
}
if os.environ.get('PORTAL_ENCRYPTION_KEYS_FILE'):
    PORTAL_ENCRYPTION_KEYS = [key.strip() for key in Path(os.environ['PORTAL_ENCRYPTION_KEYS_FILE']).read_text().splitlines() if key.strip()]
AUTHENTICATION_BACKENDS = ['apps.accounts.backends.EmailBackend']
if os.environ.get('PORTAL_AUTH_MODE', 'local') == 'oidc':
    INSTALLED_APPS += ['mozilla_django_oidc']
    AUTHENTICATION_BACKENDS = ['apps.accounts.oidc.PortalOIDCBackend', 'apps.accounts.backends.EmailBackend']
    OIDC_OP_ISSUER = os.environ['OIDC_OP_ISSUER']
    OIDC_RP_CLIENT_ID = os.environ['OIDC_RP_CLIENT_ID']
    OIDC_RP_CLIENT_SECRET = secret_value('OIDC_RP_CLIENT_SECRET')
    OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ['OIDC_OP_AUTHORIZATION_ENDPOINT']
    OIDC_OP_TOKEN_ENDPOINT = os.environ['OIDC_OP_TOKEN_ENDPOINT']
    OIDC_OP_USER_ENDPOINT = os.environ['OIDC_OP_USER_ENDPOINT']
    OIDC_OP_JWKS_ENDPOINT = os.environ['OIDC_OP_JWKS_ENDPOINT']
    OIDC_RP_SIGN_ALGO = 'RS256'
    OIDC_CALLBACK_CLASS = 'apps.accounts.oidc_views.PortalOIDCCallbackView'
    OIDC_CREATE_USER = False
    OIDC_TIMEOUT = 15
    OIDC_USE_PKCE = True
