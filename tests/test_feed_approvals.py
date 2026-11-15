import base64

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.models import User, GroupGrant, CatalogGrant
from apps.changes.installations import submit_installation, decide_installation
from apps.changes.executor import execute_next
from apps.inventory.catalog import save_address, save_address_group
from apps.inventory.models import ThreatFeed, FeedAccount
from apps.inventory.threat_feeds import save_feed_account
from apps.firewalls.models import FirewallGroup

pytestmark = pytest.mark.django_db
PASSWORD = 'feed-secret-92!Long'


@pytest.fixture
def feed_setup():
    requester = User.objects.create_user('feed-requester', is_superuser=True)
    approver = User.objects.create_user('feed-approver', is_superuser=True)
    scope = FirewallGroup.objects.create(name='HQ Firewall Group')
    ip = save_address(actor=requester, name='ip', kind='subnet', value='192.0.2.1')
    domain = save_address(actor=requester, name='domain', kind='fqdn', value='example.com')
    group = save_address_group(actor=requester, name='IOC', member_ids=[ip.pk, domain.pk])
    account = save_feed_account(actor=requester, username='collector', password=PASSWORD, feeds=[])
    return requester, approver, scope, group, ip, account


def submit(setup, key='initial', groups=None, scope=None):
    actor, _, firewall_group, address_group, _, _ = setup
    return submit_installation(actor=actor, object_ids=[], group_ids=groups or [address_group.pk],
                               target_kind='threat_feeds', firewall_group_id=(scope or firewall_group).pk,
                               idempotency_key=key)


def approve_and_execute(setup, item):
    decide_installation(actor=setup[1], request_id=item.pk, status='APPROVED')
    result = execute_next(owner_id='feed-tests')
    assert result.pk == item.pk
    return result


def get_feed(client, feed, filename='ip_list.txt'):
    header = 'Basic ' + base64.b64encode(f'collector:{PASSWORD}'.encode()).decode()
    return client.get(f'/threat-feeds/{feed.scope.slug}/{feed.slug}/{filename}', HTTP_AUTHORIZATION=header)


def change_ip(setup):
    ip = setup[4]
    ip.entry.refresh_from_db()
    return save_address(actor=setup[0], name='ip', kind='subnet', value='192.0.2.2',
                        entry_id=ip.entry_id, expected_revision=ip.entry.revision)


def test_approval_gates_initial_and_updated_frozen_content(client, feed_setup):
    actor, _, scope, group, ip, account = feed_setup
    first = submit(feed_setup)
    assert first.approval_status == 'PENDING'
    assert not first.targets.exists()
    assert execute_next(owner_id='feed-tests') is None
    assert not ThreatFeed.objects.filter(scope__firewall_group=scope).exists()
    # Submission freezes content even if the catalog changes before approval.
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.2', entry_id=ip.entry_id, expected_revision=1)
    assert approve_and_execute(feed_setup, first).execution_status == 'SUCCEEDED'
    feed = ThreatFeed.objects.get(scope__firewall_group=scope, group=group)
    account.feeds.add(feed)
    assert get_feed(client, feed).content == b'192.0.2.1/32\n'
    assert get_feed(client, feed, 'domain_list.txt').content == b'example.com\n'
    assert feed.revision == 1 and feed.approved_request_id == first.pk
    update = submit(feed_setup, 'update')
    assert get_feed(client, feed).content == b'192.0.2.1/32\n'
    assert approve_and_execute(feed_setup, update).execution_status == 'SUCCEEDED'
    assert get_feed(client, feed).content == b'192.0.2.2/32\n'


@pytest.mark.parametrize('status', ['REJECTED', 'CANCELLED'])
def test_rejected_or_cancelled_update_keeps_previous_version(client, feed_setup, status):
    approve_and_execute(feed_setup, submit(feed_setup))
    change_ip(feed_setup)
    feed = ThreatFeed.objects.get(group=feed_setup[3])
    feed_setup[5].feeds.add(feed)
    update = submit(feed_setup, 'pending-update')
    actor = feed_setup[0] if status == 'CANCELLED' else feed_setup[1]
    decide_installation(actor=actor, request_id=update.pk, status=status)
    assert execute_next(owner_id='feed-tests') is None
    assert get_feed(client, feed).content == b'192.0.2.1/32\n'


def test_scoped_assignments_and_same_group_independent_versions(client, feed_setup):
    approve_and_execute(feed_setup, submit(feed_setup))
    other = FirewallGroup.objects.create(name='Branch Firewall Group')
    approve_and_execute(feed_setup, submit(feed_setup, 'other-scope', scope=other))
    first = ThreatFeed.objects.get(scope__firewall_group=feed_setup[2])
    second = ThreatFeed.objects.get(scope__firewall_group=other)
    feed_setup[5].feeds.add(first)
    assert get_feed(client, first).status_code == 200
    assert get_feed(client, second).status_code == 404
    assert client.get('/threat-feeds/ioc/ip_list.txt').status_code == 404
    feed_setup[2].enabled = False
    feed_setup[2].save()
    assert get_feed(client, first).status_code == 404


def test_out_of_order_approval_cannot_overwrite_newer_publication(feed_setup):
    first = submit(feed_setup, 'older')
    second = submit(feed_setup, 'newer')
    assert approve_and_execute(feed_setup, second).execution_status == 'SUCCEEDED'
    assert approve_and_execute(feed_setup, first).execution_status == 'FAILED'
    assert ThreatFeed.objects.get(group=feed_setup[3]).approved_request_id == second.pk


def test_superadmin_requires_explicit_approval_and_revoked_permissions_fail(feed_setup):
    item = submit(feed_setup)
    assert execute_next(owner_id='feed-tests') is None
    decide_installation(actor=feed_setup[0], request_id=item.pk, status='APPROVED')
    item.refresh_from_db()
    assert item.self_approved
    feed_setup[0].is_active = False
    feed_setup[0].save()
    assert execute_next(owner_id='feed-tests').execution_status == 'FAILED'
    assert not ThreatFeed.objects.filter(scope__isnull=False).exists()


def test_direct_publication_cannot_bypass_approval(feed_setup):
    from apps.inventory.threat_feeds import publish_group
    with pytest.raises(ValidationError, match='request'):
        publish_group(actor=feed_setup[0], group=feed_setup[3], enabled=True)


def test_submission_requires_admin_catalog_and_group_rights(feed_setup):
    actor = User.objects.create_user('ordinary-requester')
    CatalogGrant.objects.create(user=actor, capability='catalog_view')
    for cap in ('view', 'submit'):
        GroupGrant.objects.create(user=actor, firewall_group=feed_setup[2], capability=cap)
    data = list(feed_setup)
    data[0] = actor
    with pytest.raises(PermissionDenied):
        submit(data)
    actor.groups.add(Group.objects.get_or_create(name='Administrator')[0])
    item = submit(data)
    assert item.snapshot['target_kind'] == 'threat_feeds'
    GroupGrant.objects.filter(user=actor, capability='submit').delete()
    with pytest.raises(PermissionDenied):
        decide_installation(actor=feed_setup[1], request_id=item.pk, status='APPROVED')


def test_new_request_target_preview_queue_and_history(client, feed_setup):
    actor, approver, scope, group, _, _ = feed_setup
    client.force_login(actor)
    assert b'Threat Feeds' in client.get(reverse('new_request')).content
    data = {'target_kind':'threat_feeds', 'firewall_group':scope.pk, 'groups':[group.pk],
            'idempotency_key':'feed-form', 'action':'preview'}
    response = client.post(reverse('new_request'), data)
    assert response.status_code == 200 and b'192.0.2.1/32' in response.content
    assert b'hq_firewall_group/ioc/ip_list.txt' in response.content
    data['action'] = 'submit'
    assert client.post(reverse('new_request'), data).status_code == 302
    client.force_login(approver)
    assert b'Threat Feeds' in client.get(reverse('approvals')).content
    assert b'Threat Feeds' in client.get(reverse('history')).content


def test_revocation_blocks_stale_reenable_and_direct_enable(client, feed_setup):
    from apps.inventory.threat_feeds import disable_feed
    approve_and_execute(feed_setup, submit(feed_setup))
    change_ip(feed_setup)
    feed = ThreatFeed.objects.get(group=feed_setup[3])
    pending = submit(feed_setup, 'before-revocation')
    disable_feed(actor=feed_setup[0], pk=feed.pk)
    client.force_login(feed_setup[0])
    client.post(reverse('threat_feed_edit', args=[feed.pk]), {'enabled':'on'})
    feed.refresh_from_db()
    assert not feed.enabled
    assert approve_and_execute(feed_setup, pending).execution_status == 'FAILED'
    assert approve_and_execute(feed_setup, submit(feed_setup, 'after-revocation')).execution_status == 'SUCCEEDED'


def test_multi_group_publication_rolls_back_if_one_revision_is_stale(feed_setup):
    from apps.inventory.threat_feeds import disable_feed
    other = save_address_group(actor=feed_setup[0], name='Second IOC', member_ids=[feed_setup[4].pk])
    groups = [feed_setup[3].pk, other.pk]
    first = submit(feed_setup, groups=groups)
    approve_and_execute(feed_setup, first)
    change_ip(feed_setup)
    pending = submit(feed_setup, 'both-update', groups=groups)
    disable_feed(actor=feed_setup[0], pk=ThreatFeed.objects.get(group=other).pk)
    assert approve_and_execute(feed_setup, pending).execution_status == 'FAILED'
    original = ThreatFeed.objects.get(group=feed_setup[3])
    assert original.revision == 1 and original.approved_request_id == first.pk


def test_tampered_approved_snapshot_is_not_published(feed_setup):
    from apps.changes.models import InstallationRequest
    item = submit(feed_setup)
    decide_installation(actor=feed_setup[1], request_id=item.pk, status='APPROVED')
    item.snapshot['groups'][0]['domain_text'] = 'unapproved.example\n'
    InstallationRequest.objects.filter(pk=item.pk).update(snapshot=item.snapshot)
    assert execute_next(owner_id='feed-tests').execution_status == 'FAILED'
    assert not ThreatFeed.objects.filter(scope__isnull=False).exists()


def test_feed_recovery_retries_local_transaction_without_device_calls(feed_setup, monkeypatch):
    from apps.changes.models import InstallationRequest
    from apps.changes.executor import recover_locked_execution
    import apps.changes.installation_executor as device_executor
    monkeypatch.setattr(device_executor, 'FortinetClient', lambda *args, **kwargs: pytest.fail('Feed must not contact FortiGate'))
    item = submit(feed_setup)
    decide_installation(actor=feed_setup[1], request_id=item.pk, status='APPROVED')
    # Acquire the shared runner lease without claiming this request.
    from apps.changes.executor import acquire_lease
    acquire_lease('feed-tests')
    InstallationRequest.objects.filter(pk=item.pk).update(execution_status='RUNNING')
    recover_locked_execution(owner_id='feed-tests')
    item.refresh_from_db()
    assert item.execution_status == 'PENDING' and not item.recovery_required
    assert execute_next(owner_id='feed-tests').execution_status == 'SUCCEEDED'
    assert execute_next(owner_id='feed-tests') is None
    assert ThreatFeed.objects.get(group=feed_setup[3]).revision == 1


def test_feed_recovery_does_not_change_device_reconciliation_policy(feed_setup):
    from apps.changes.models import InstallationRequest
    from apps.changes.executor import acquire_lease, recover_locked_execution
    acquire_lease('feed-tests')
    item = InstallationRequest.objects.create(requester=feed_setup[0], snapshot={'target_kind':'firewall_group'},
                                               payload_digest='x'*64, idempotency_key='device', execution_status='RUNNING')
    recover_locked_execution(owner_id='feed-tests')
    item.refresh_from_db()
    assert item.execution_status == 'RECONCILIATION_REQUIRED' and item.recovery_required


def test_standalone_objects_and_empty_selection_cannot_publish(feed_setup):
    for objects, groups in [([feed_setup[4].pk], [feed_setup[3].pk]), ([], [])]:
        with pytest.raises(ValidationError):
            submit_installation(actor=feed_setup[0], object_ids=objects, group_ids=groups,
                                target_kind='threat_feeds', firewall_group_id=feed_setup[2].pk, idempotency_key='invalid')


def test_approver_permission_revocation_and_missing_view_blocks_execution(feed_setup):
    actor = User.objects.create_user('scoped-approver')
    for cap in ('view', 'approve'):
        GroupGrant.objects.create(user=actor, firewall_group=feed_setup[2], capability=cap)
    item = submit(feed_setup)
    decide_installation(actor=actor, request_id=item.pk, status='APPROVED')
    GroupGrant.objects.filter(user=actor, capability='view').delete()
    assert execute_next(owner_id='feed-tests').execution_status == 'FAILED'
    assert not ThreatFeed.objects.filter(scope__isnull=False).exists()


def test_namespace_and_address_slugs_remain_stable_after_renames(feed_setup):
    approve_and_execute(feed_setup, submit(feed_setup))
    feed = ThreatFeed.objects.get(group=feed_setup[3])
    scope_slug, group_slug = feed.scope.slug, feed.slug
    feed_setup[2].name = 'Renamed scope'
    feed_setup[2].save()
    feed_setup[3].entry.name = 'Renamed IOC'
    feed_setup[3].entry.save()
    change_ip(feed_setup)
    approve_and_execute(feed_setup, submit(feed_setup, 'renamed'))
    feed.refresh_from_db()
    assert feed.scope.slug == scope_slug and feed.slug == group_slug


def test_request_idempotency_and_preview_has_no_publication_side_effects(feed_setup):
    from apps.changes.installations import build_snapshot
    from apps.inventory.models import ThreatFeedScope
    build_snapshot(actor=feed_setup[0], object_ids=[], group_ids=[feed_setup[3].pk], target_kind='threat_feeds', firewall_group_id=feed_setup[2].pk)
    assert not ThreatFeedScope.objects.exists() and not ThreatFeed.objects.exists()
    item = submit(feed_setup)
    assert submit(feed_setup).pk == item.pk


def test_unknown_assignments_are_rejected_and_short_urls_are_not_supported(client, feed_setup):
    approve_and_execute(feed_setup, submit(feed_setup))
    missing = ThreatFeed(pk=999999)
    with pytest.raises(ValidationError):
        save_feed_account(actor=feed_setup[0], username='invalid-access', password=PASSWORD, feeds=[missing])
    assert client.get('/threat-feeds/ioc/ip_list.txt').status_code == 404
    client.force_login(feed_setup[0])
    assert b'legacy' not in client.get(reverse('threat_feeds')).content.lower()


def test_catalog_group_deletion_reports_publication_dependency(feed_setup):
    from apps.inventory.catalog import delete_catalog_entry
    approve_and_execute(feed_setup, submit(feed_setup))
    with pytest.raises(ValidationError, match='Threat Feed'):
        delete_catalog_entry(actor=feed_setup[0], entry_id=feed_setup[3].entry_id, expected_revision=1)


def test_separate_pending_requests_reserve_colliding_address_group_slugs(feed_setup):
    first_group = save_address_group(actor=feed_setup[0], name='IOC A', member_ids=[feed_setup[4].pk])
    second_group = save_address_group(actor=feed_setup[0], name='IOC_A', member_ids=[])
    first = submit(feed_setup, 'collision-first', groups=[first_group.pk])
    second = submit(feed_setup, 'collision-second', groups=[second_group.pk])
    assert first.snapshot['groups'][0]['slug'] == 'ioc_a'
    assert second.snapshot['groups'][0]['slug'] == 'ioc_a_2'
    assert not ThreatFeed.objects.exists()
    assert approve_and_execute(feed_setup, first).execution_status == 'SUCCEEDED'
    assert approve_and_execute(feed_setup, second).execution_status == 'SUCCEEDED'
