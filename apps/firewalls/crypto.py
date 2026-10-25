from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def keyring():
    try:
        keys = settings.PORTAL_ENCRYPTION_KEYS
        if not keys:
            raise ValueError
        return MultiFernet([Fernet(key.encode() if isinstance(key, str) else key) for key in keys])
    except (AttributeError, ValueError, TypeError):
        raise ImproperlyConfigured('Configure a valid external encryption key ring.') from None


def encrypt_secret(value: str) -> str:
    return 'v1:' + keyring().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value.startswith('v1:'):
        raise ValueError('Unsupported credential format.')
    try:
        return keyring().decrypt(value[3:].encode()).decode()
    except InvalidToken:
        raise ValueError('Credential cannot be decrypted with the configured keys.') from None
