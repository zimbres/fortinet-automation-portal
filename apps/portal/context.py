import tomllib
from django.conf import settings

with (settings.BASE_DIR / 'pyproject.toml').open('rb') as project_metadata:
    APP_VERSION = tomllib.load(project_metadata)['project']['version']


def portal_context(request):
    from apps.accounts.permissions import can_manage_restrictions
    return {'app_version':APP_VERSION, 'oidc_enabled':'mozilla_django_oidc' in settings.INSTALLED_APPS,
            'can_manage_restrictions':can_manage_restrictions(request.user)}
