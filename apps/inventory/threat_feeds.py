"""Publication and feed-only credential management. No portal authentication."""
import re

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.permissions import can_manage_restrictions
from apps.audit.services import record_event
from config.public_url import normalize_public_url  # Public validation interface.
from .models import FeedAccount, ThreatFeed


def require_feed_management(user):
    if not can_manage_restrictions(user):
        raise PermissionDenied('Threat feed management requires Administrator or Superadministrator access.')


def publish_group(*, actor, group, enabled=True):
    require_feed_management(actor)
    raise ValidationError('Submit a Threat Feeds request for approval to publish or update content.')


@transaction.atomic
def disable_feed(*, actor, pk):
    require_feed_management(actor)
    feed = ThreatFeed.objects.get(pk=pk)
    feed.enabled = False
    feed.revision += 1
    feed.save(update_fields=['enabled', 'revision'])
    record_event(actor=actor, event_type='threat_feed.disabled', metadata={'target_id':feed.pk})
    return feed

def save_feed_account(*, actor, username, password, feeds, is_active=True, account_id=None):
    require_feed_management(actor)
    username = username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.@+-]{1,150}', username):
        raise ValidationError('Use 1–150 letters, numbers, or . @ + - _ for the feed username.')
    ids = {feed.pk for feed in feeds}
    if ThreatFeed.objects.filter(pk__in=ids, approved_request__isnull=False).count() != len(ids):
        raise ValidationError('Select existing approved publications.')
    if not account_id and not password:
        raise ValidationError('A password is required for a new feed account.')
    if len(password.encode('utf-8')) > 4096:
        raise ValidationError('The feed password is too long. Use at most 4096 UTF-8 bytes.')
    if password:
        validate_password(password, user=FeedAccount(username=username))
    try:
        with transaction.atomic():
            account = FeedAccount.objects.get(pk=account_id) if account_id else FeedAccount()
            account.username = username
            account.is_active = is_active
            if password:
                account.password = make_password(password)
            account.save()
            account.feeds.set(ids)
            record_event(actor=actor, event_type='threat_feed.account_saved', metadata={
                'target_id':account.pk, 'username':account.username, 'count':len(ids),
                'status':'enabled' if is_active else 'disabled',
            })
            return account
    except (IntegrityError, FeedAccount.DoesNotExist):
        raise ValidationError('This username is already used or the account changed. Reload and try again.') from None


@transaction.atomic
def delete_feed_configuration(*, actor, pk, account=False):
    require_feed_management(actor)
    model = FeedAccount if account else ThreatFeed
    record = model.objects.get(pk=pk)
    record_event(actor=actor, event_type='threat_feed.account_deleted' if account else 'threat_feed.deleted',
                 metadata={'target_id':record.pk})
    if not account:
        # Retain a revision tombstone so old pending requests cannot resurrect access.
        disable_feed(actor=actor, pk=record.pk)
        record.accounts.clear()
    else:
        record.delete()
