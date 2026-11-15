"""Validate the explicitly configured public origin and optional mount path."""
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def normalize_public_url(value):
    if not value:
        return 'http://127.0.0.1:8000'
    try:
        parsed = urlsplit(value)
        decoded_path = unquote(parsed.path)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or '?' in value or '#' in value or '\\' in value
                or any(c.isspace() or ord(c) < 32 for c in value)
                or any(part in ('.', '..') for part in decoded_path.split('/'))
                or decoded_path.startswith('//')):
            raise ValueError
        parsed.port  # Validate numeric port and range.
    except ValueError:
        raise ImproperlyConfigured('APP_PUBLIC_URL must be an absolute HTTP/HTTPS URL without credentials, query, or fragment.') from None
    return value.rstrip('/')
