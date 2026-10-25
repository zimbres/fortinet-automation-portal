"""Local development only. Never use this module for deployment."""
import os
from pathlib import Path
from .local_oidc import load_local_oidc

load_local_oidc(os.environ, Path(__file__).resolve().parents[2])

from .base import *  # noqa: F403

SECRET_KEY = secret_value('DJANGO_SECRET_KEY', default='development-only-not-for-production-fortinet-portal')
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
DATA_DIR.mkdir(parents=True, exist_ok=True)
if not PORTAL_ENCRYPTION_KEYS and not os.environ.get('PORTAL_ENCRYPTION_KEYS_FILE'):
    local_keys = BASE_DIR / '.cache' / 'encryption.keys'
    if local_keys.is_file():
        PORTAL_ENCRYPTION_KEYS = [key.strip() for key in local_keys.read_text().splitlines() if key.strip()]
