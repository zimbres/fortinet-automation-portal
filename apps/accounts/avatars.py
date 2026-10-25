"""Store validated, re-encoded profile pictures without modifying identity fields."""
from django.db import transaction
from apps.audit.services import record_event


def set_avatar(account, upload=None):
    storage = account.avatar.storage
    old_name = account.avatar.name
    new_name = None
    try:
        with transaction.atomic():
            if upload is None:
                account.avatar = ''
            else:
                account.avatar.save(upload.name, upload, save=False)
                new_name = account.avatar.name
            account.save(update_fields=['avatar'])
            record_event(actor=account, event_type='account.avatar_updated')
            if old_name and old_name != new_name:
                transaction.on_commit(lambda: storage.delete(old_name))
    except Exception:
        if new_name:
            storage.delete(new_name)
        raise
