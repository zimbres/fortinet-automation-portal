import base64

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.models import User
from apps.inventory.catalog import save_address, save_address_group

pytestmark = pytest.mark.django_db
PASSWORD = 'feed-only-Secret-9482!'


def basic(username='collector', password=PASSWORD):
    return 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()


def approved_publication(actor, group, firewall_group):
    import uuid
    from apps.changes.installations import submit_installation, decide_installation
    from apps.changes.executor import execute_next
    from apps.inventory.models import ThreatFeed
    item = submit_installation(actor=actor, object_ids=[], group_ids=[group.pk], target_kind='threat_feeds',
                               firewall_group_id=firewall_group.pk, idempotency_key=str(uuid.uuid4()))
    decide_installation(actor=actor, request_id=item.pk, status='APPROVED')
    assert execute_next(owner_id='feed-security-tests').execution_status == 'SUCCEEDED'
    return ThreatFeed.objects.get(group=group, scope__firewall_group=firewall_group)


@pytest.fixture
def published():
    from apps.inventory.threat_feeds import save_feed_account
    from apps.firewalls.models import FirewallGroup
    actor = User.objects.create_user('feed-admin', is_superuser=True)
    addresses = [save_address(actor=actor, name=name, kind=kind, value=value) for name, kind, value in [
        ('host', 'subnet', '192.0.2.1'), ('network', 'subnet', '198.51.100.0/24'),
        ('domain', 'fqdn', 'example.com'), ('wildcard', 'wildcard_fqdn', '*.example.org'),
        ('duplicate', 'fqdn', 'example.com'),
    ]]
    group = save_address_group(actor=actor, name='My Address', member_ids=[a.pk for a in addresses])
    feed = approved_publication(actor, group, FirewallGroup.objects.create(name='Edge'))
    account = save_feed_account(actor=actor, username='collector', password=PASSWORD, feeds=[feed], is_active=True)
    return actor, group, feed, account


def test_approved_split_plain_text_and_head(client, published):
    actor, group, feed, _ = published
    assert feed.slug == 'my_address'
    url = '/threat-feeds/edge/my_address/ip_list.txt'
    response = client.get(url, HTTP_AUTHORIZATION=basic())
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.content == b'192.0.2.1/32\n198.51.100.0/24\n'
    assert 'no-store' in response['Cache-Control']
    assert client.head(url, HTTP_AUTHORIZATION=basic()).content == b''
    domains = client.get('/threat-feeds/edge/my_address/domain_list.txt', HTTP_AUTHORIZATION=basic())
    assert domains.content == b'*.example.org\nexample.com\n'
    group.members.clear()
    assert client.get(url, HTTP_AUTHORIZATION=basic()).content == b'192.0.2.1/32\n198.51.100.0/24\n'
    approved_publication(actor, group, feed.scope.firewall_group)
    assert client.get(url, HTTP_AUTHORIZATION=basic()).content == b''
    assert client.post(url, HTTP_AUTHORIZATION=basic()).status_code == 405


@pytest.mark.parametrize('header', ['', 'Bearer abc', 'Basic !!!', 'Basic YQ==', 'Basic /w==', basic(password='wrong'), 'Basic'])
def test_basic_auth_required_even_with_portal_session(client, published, header):
    client.force_login(published[0])
    response = client.get('/threat-feeds/edge/my_address/ip_list.txt', HTTP_AUTHORIZATION=header)
    assert response.status_code == 401
    assert response['WWW-Authenticate'].startswith('Basic ')
    assert 'no-store' in response['Cache-Control']


def test_explicit_assignments_and_immediate_revocation(client, published):
    _, _, feed, account = published
    url = '/threat-feeds/edge/my_address/ip_list.txt'
    account.feeds.clear()
    assert client.get(url, HTTP_AUTHORIZATION=basic()).status_code == 404
    account.feeds.add(feed)
    feed.enabled = False
    feed.save()
    assert client.get(url, HTTP_AUTHORIZATION=basic()).status_code == 404
    feed.enabled = True
    feed.save()
    account.is_active = False
    account.save()
    assert client.get(url, HTTP_AUTHORIZATION=basic()).status_code == 401


def test_feed_credentials_cannot_authenticate_portal(published):
    account = published[3]
    assert account.password != PASSWORD
    assert authenticate(username='collector', password=PASSWORD) is None


def test_stable_slug_collisions_and_group_deletion(client, published):
    from django.db.models.deletion import ProtectedError
    actor, group, feed, account = published
    group.entry.name = 'Renamed'
    group.entry.save()
    feed.refresh_from_db()
    assert feed.slug == 'my_address'
    other = save_address_group(actor=actor, name='my_address', member_ids=[])
    second = approved_publication(actor, other, feed.scope.firewall_group)
    assert second.slug != feed.slug
    with pytest.raises(ProtectedError):
        group.entry.delete()
    assert account.feeds.filter(pk=feed.pk).exists()


def test_service_authorization_and_secret_free_audit(published):
    from apps.audit.models import AuditEvent
    from apps.inventory.threat_feeds import publish_group, save_feed_account
    _, group, feed, _ = published
    operator = User.objects.create_user('feed-operator')
    with pytest.raises(PermissionDenied):
        publish_group(actor=operator, group=group, enabled=True)
    with pytest.raises(PermissionDenied):
        save_feed_account(actor=operator, username='forged', password=PASSWORD, feeds=[feed], is_active=True)
    assert PASSWORD not in str(list(AuditEvent.objects.values_list('metadata', flat=True)))


@pytest.mark.parametrize('is_superuser', [True, False])
def test_management_and_public_urls(client, published, settings, is_superuser):
    actor, group, feed, account = published
    if not is_superuser:
        actor.is_superuser = False
        actor.save()
        actor.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    settings.APP_PUBLIC_URL = 'https://feeds.example.com/portal'
    client.force_login(actor)
    response = client.get(reverse('threat_feeds'))
    assert response.status_code == 200
    assert b'https://feeds.example.com/portal/threat-feeds/edge/my_address/ip_list.txt' in response.content
    assert b'https://feeds.example.com/portal/threat-feeds/edge/my_address/domain_list.txt' in response.content
    response = client.post(reverse('feed_account_edit', args=[account.pk]), {
        'username':account.username, 'password':'', 'is_active':'on', 'feeds':[],
    })
    assert response.status_code == 302
    assert not account.feeds.exists()


def test_management_denies_operator(client, published):
    client.force_login(User.objects.create_user('ordinary-user'))
    assert client.get(reverse('threat_feeds')).status_code == 403
    assert client.post(reverse('threat_feed_new'), {'group':published[1].pk, 'enabled':'on'}).status_code == 403
    assert client.post(reverse('feed_account_new'), {'username':'intruder', 'password':PASSWORD}).status_code == 403


def test_password_validation_rotation_and_unset_public_url(client, published, settings):
    actor, _, feed, account = published
    from apps.inventory.threat_feeds import save_feed_account
    with pytest.raises(ValidationError):
        save_feed_account(actor=actor, username='weak', password='123', feeds=[], is_active=True)
    save_feed_account(actor=actor, account_id=account.pk, username=account.username,
                      password='replacement-Secret-987!', feeds=[feed], is_active=True)
    assert client.get('/threat-feeds/edge/my_address/ip_list.txt', HTTP_AUTHORIZATION=basic()).status_code == 401
    assert client.get('/threat-feeds/edge/my_address/ip_list.txt', HTTP_AUTHORIZATION=basic(password='replacement-Secret-987!')).status_code == 200
    settings.APP_PUBLIC_URL = ''
    client.force_login(actor)
    response = client.get(reverse('threat_feeds'))
    assert b'http://127.0.0.1:8000/threat-feeds/edge/my_address/ip_list.txt' in response.content
    assert b'http://127.0.0.1:8000/threat-feeds/edge/my_address/domain_list.txt' in response.content


@pytest.mark.parametrize('value,expected', [
    ('', 'http://127.0.0.1:8000'), ('https://portal.example.com/', 'https://portal.example.com'),
    ('http://app:3001/portal/', 'http://app:3001/portal'),
])
def test_public_url_normalization(value, expected):
    from apps.inventory.threat_feeds import normalize_public_url
    assert normalize_public_url(value) == expected


@pytest.mark.parametrize('value', ['portal.example.com', '//example.com', 'ftp://example.com', 'https://u:p@example.com',
                                 'https://example.com?q=x', 'https://example.com/#fragment', 'https://example.com:abc',
                                 'https://example.com/../bad', 'https://example.com\n'])
def test_invalid_public_url(value):
    from apps.inventory.threat_feeds import normalize_public_url
    from django.core.exceptions import ImproperlyConfigured
    with pytest.raises(ImproperlyConfigured):
        normalize_public_url(value)


def test_required_password_change_session_does_not_intercept_feed_auth(client, published):
    actor = published[0]
    actor.set_password('portal-password-only-928!')
    actor.require_password_change = True
    actor.save()
    client.force_login(actor)
    assert client.get('/threat-feeds/edge/my_address/ip_list.txt', HTTP_AUTHORIZATION=basic()).status_code == 200


@pytest.mark.parametrize('name', ['threat_feed_edit', 'threat_feed_delete', 'feed_account_edit', 'feed_account_delete'])
def test_every_management_action_requires_admin(client, published, name):
    client.force_login(User.objects.create_user('no-feed-permission'))
    pk = published[3].pk if name.startswith('feed_account') else published[2].pk
    assert client.get(reverse(name, args=[pk])).status_code == 403
    assert client.post(reverse(name, args=[pk]), {}).status_code == 403


def test_create_edit_delete_configuration_with_csrf_and_audit(client, published):
    from django.test import Client
    from apps.inventory.models import FeedAccount, ThreatFeed
    from apps.audit.models import AuditEvent
    actor, group, feed, account = published
    client.force_login(actor)
    new_group = save_address_group(actor=actor, name='Second feed', member_ids=[])
    response = client.post(reverse('threat_feed_new'), {'group':new_group.pk, 'enabled':'on'})
    assert response.status_code == 302
    assert not ThreatFeed.objects.filter(group=new_group).exists()
    second = approved_publication(actor, new_group, feed.scope.firewall_group)
    response = client.post(reverse('feed_account_new'), {
        'username':'second-collector', 'password':PASSWORD, 'is_active':'on', 'feeds':[second.pk],
    })
    assert response.status_code == 302
    assert FeedAccount.objects.get(username='second-collector').feeds.get() == second
    assert client.get('/threat-feeds/edge/my_address/domain_list.txt', HTTP_AUTHORIZATION=basic(username='second-collector')).status_code == 404
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(actor)
    assert csrf_client.post(reverse('feed_account_delete', args=[account.pk])).status_code == 403
    response = client.post(reverse('threat_feed_edit', args=[feed.pk]), {'action':'disable'})
    assert response.status_code == 302
    feed.refresh_from_db()
    assert feed.group == group and not feed.enabled
    assert client.get(reverse('threat_feed_delete', args=[feed.pk])).status_code == 200
    assert ThreatFeed.objects.filter(pk=feed.pk).exists()
    assert client.post(reverse('threat_feed_delete', args=[feed.pk])).status_code == 302
    assert ThreatFeed.objects.filter(pk=feed.pk, enabled=False).exists()
    assert not account.feeds.exists()
    assert client.post(reverse('feed_account_delete', args=[account.pk])).status_code == 302
    assert not FeedAccount.objects.filter(pk=account.pk).exists()
    assert AuditEvent.objects.filter(event_type='threat_feed.deleted').exists()
    assert AuditEvent.objects.filter(event_type='threat_feed.account_deleted').exists()


def test_invalid_account_forms_do_not_mutate_assignments(client, published):
    actor, _, feed, account = published
    client.force_login(actor)
    before = account.password
    response = client.post(reverse('feed_account_edit', args=[account.pk]), {
        'username':account.username, 'password':'123', 'is_active':'on', 'feeds':[feed.pk],
    })
    assert response.status_code == 200
    account.refresh_from_db()
    assert account.password == before
    assert client.post(reverse('feed_account_new'), {'username':'new', 'password':''}).status_code == 200
    assert client.post(reverse('feed_account_new'), {
        'username':account.username, 'password':PASSWORD, 'feeds':[feed.pk],
    }).status_code == 200


def test_anonymous_and_inactive_managers_cannot_manage(client, published):
    assert client.get(reverse('threat_feeds')).status_code == 302
    actor = published[0]
    actor.is_active = False
    actor.save()
    from apps.inventory.threat_feeds import publish_group
    with pytest.raises(PermissionDenied):
        publish_group(actor=actor, group=published[1], enabled=True)


def test_portal_password_does_not_authorize_feed(client, published):
    actor = published[0]
    actor.set_password(PASSWORD)
    actor.save()
    assert client.get('/threat-feeds/edge/my_address/ip_list.txt',
                      HTTP_AUTHORIZATION=basic(username=actor.username)).status_code == 401


def test_public_url_is_validated_when_settings_load():
    import os
    import subprocess
    import sys
    env = {**os.environ, 'APP_PUBLIC_URL':'https://user:secret@example.com', 'PORTAL_AUTH_MODE':'local'}
    result = subprocess.run([sys.executable, '-c', 'import config.settings.base'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'APP_PUBLIC_URL must be' in result.stderr


@pytest.mark.parametrize('configured', [False, True], ids=['unset', 'empty'])
def test_public_url_settings_default(configured):
    import os
    import subprocess
    import sys
    env = {**os.environ, 'PORTAL_AUTH_MODE':'local'}
    env.pop('APP_PUBLIC_URL', None)
    if configured:
        env['APP_PUBLIC_URL'] = ''
    result = subprocess.run([sys.executable, '-c',
                             'from config.settings.base import APP_PUBLIC_URL; print(APP_PUBLIC_URL)'],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'http://127.0.0.1:8000'


@pytest.mark.parametrize('password', ['x' * 4090 + 'Ab9!xy', 'é' * 1600 + 'Ab9!'], ids=['ascii-boundary', 'multibyte'])
def test_saved_long_password_can_download(client, published, password):
    from apps.inventory.threat_feeds import save_feed_account
    actor, _, feed, account = published
    save_feed_account(actor=actor, account_id=account.pk, username=account.username,
                      password=password, feeds=[feed], is_active=True)
    assert client.get('/threat-feeds/edge/my_address/ip_list.txt', HTTP_AUTHORIZATION=basic(password=password)).status_code == 200


@pytest.mark.parametrize('password', ['x' * 4097, 'é' * 2049], ids=['ascii-oversized', 'multibyte-oversized'])
def test_oversized_password_is_rejected(published, password):
    from apps.inventory.threat_feeds import save_feed_account
    with pytest.raises(ValidationError):
        save_feed_account(actor=published[0], username='oversized', password=password, feeds=[], is_active=True)
