import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.test_feed_approvals import feed_setup, submit, approve_and_execute
from apps.inventory.models import ThreatFeed
from apps.inventory.catalog import save_address, save_address_group
from apps.changes.models import InstallationRequest
from apps.changes.installations import build_snapshot

pytestmark = pytest.mark.django_db


def test_update_link_locks_scope_and_shows_only_added_removed_values(client, feed_setup):
    actor, _, scope, group, ip, _ = feed_setup
    approve_and_execute(feed_setup, submit(feed_setup))
    feed = ThreatFeed.objects.get(group=group)
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.2', entry_id=ip.entry_id, expected_revision=1)
    client.force_login(actor)
    response = client.get(reverse('threat_feed_update_request', args=[feed.pk]))
    assert response.status_code == 200
    assert response.context['form'].fields['firewall_group'].disabled
    assert response.context['form'].fields['groups'].disabled
    assert response.context['form'].fields['target_kind'].disabled
    assert b'Added IP addresses' in response.content and b'Removed IP addresses' in response.content
    assert b'192.0.2.1/32' in response.content and b'192.0.2.2/32' in response.content
    assert b'example.com' not in response.content  # Unchanged domain is not part of this change.
    assert b'name="objects"' not in response.content
    assert reverse('threat_feed_update_request', args=[feed.pk]).encode() in client.get(reverse('threat_feeds')).content


def test_update_post_cannot_change_feed_scope(client, feed_setup):
    from apps.firewalls.models import FirewallGroup
    actor, _, scope, group, ip, _ = feed_setup
    approve_and_execute(feed_setup, submit(feed_setup))
    feed = ThreatFeed.objects.get(group=group)
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.2', entry_id=ip.entry_id, expected_revision=1)
    other_scope = FirewallGroup.objects.create(name='Other')
    other_group = save_address_group(actor=actor, name='Other group', member_ids=[])
    client.force_login(actor)
    response = client.post(reverse('threat_feed_update_request', args=[feed.pk]), {
        'target_kind':'firewall_group', 'firewall_group':other_scope.pk, 'groups':[other_group.pk],
        'expected_revision':feed.revision, 'idempotency_key':'fixed-update', 'action':'submit',
    })
    assert response.status_code == 302
    item = InstallationRequest.objects.get(idempotency_key='fixed-update')
    assert item.snapshot['target_kind'] == 'threat_feeds'
    assert item.snapshot['firewall_group_id'] == scope.pk
    assert [row['id'] for row in item.snapshot['groups']] == [group.pk]
    assert item.snapshot['groups'][0]['changes']['ip_added'] == ['192.0.2.2/32']
    assert item.snapshot['groups'][0]['changes']['ip_removed'] == ['192.0.2.1/32']


def test_no_op_requests_are_blocked_and_disabled_feed_can_be_republished(client, feed_setup):
    from apps.inventory.threat_feeds import disable_feed
    approve_and_execute(feed_setup, submit(feed_setup))
    with pytest.raises(ValidationError, match='No changes'):
        submit(feed_setup, 'no-op')
    feed = ThreatFeed.objects.get(group=feed_setup[3])
    client.force_login(feed_setup[0])
    response = client.get(reverse('threat_feed_update_request', args=[feed.pk]))
    assert b'No changes' in response.content and b'Submit for approval' not in response.content
    disable_feed(actor=feed_setup[0], pk=feed.pk)
    response = client.get(reverse('threat_feed_update_request', args=[feed.pk]))
    assert b'Enable publication' in response.content


def test_standalone_objects_are_disabled_for_feed_target_and_forged_values_rejected(client, feed_setup):
    from apps.changes.forms import InstallationForm
    actor, _, scope, group, ip, _ = feed_setup
    form = InstallationForm(user=actor, initial={'target_kind':'threat_feeds'})
    assert form.fields['objects'].disabled
    client.force_login(actor)
    response = client.post(reverse('new_request'), {
        'target_kind':'threat_feeds', 'firewall_group':scope.pk, 'groups':[group.pk], 'objects':[ip.pk],
        'idempotency_key':'forged-object', 'action':'submit',
    })
    assert response.status_code == 200
    assert not InstallationRequest.objects.filter(idempotency_key='forged-object').exists()


def test_delta_remains_frozen_for_approval_details(client, feed_setup):
    actor, _, scope, group, ip, _ = feed_setup
    approve_and_execute(feed_setup, submit(feed_setup))
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.2', entry_id=ip.entry_id, expected_revision=1)
    item = submit(feed_setup, 'frozen-diff')
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.3', entry_id=ip.entry_id, expected_revision=2)
    client.force_login(feed_setup[1])
    response = client.get(reverse('installation_detail', args=[item.pk]))
    assert b'192.0.2.1/32' in response.content and b'192.0.2.2/32' in response.content
    assert b'192.0.2.3/32' not in response.content and b'example.com' not in response.content


def test_stale_update_screen_requires_reload(client, feed_setup):
    from apps.inventory.threat_feeds import disable_feed
    actor, _, _, group, ip, _ = feed_setup
    approve_and_execute(feed_setup, submit(feed_setup))
    feed = ThreatFeed.objects.get(group=group)
    before = feed.revision
    disable_feed(actor=actor, pk=feed.pk)
    client.force_login(actor)
    response = client.post(reverse('threat_feed_update_request', args=[feed.pk]), {
        'expected_revision':before, 'idempotency_key':'stale-screen', 'action':'submit',
    })
    assert response.status_code == 200
    assert not InstallationRequest.objects.filter(idempotency_key='stale-screen').exists()


def test_only_changed_groups_are_included_in_multi_feed_request(feed_setup):
    actor, _, scope, group, ip, _ = feed_setup
    other = save_address_group(actor=actor, name='Unchanged', member_ids=[])
    approve_and_execute(feed_setup, submit(feed_setup, groups=[group.pk, other.pk]))
    save_address(actor=actor, name='ip', kind='subnet', value='192.0.2.2', entry_id=ip.entry_id, expected_revision=1)
    snapshot = build_snapshot(actor=actor, object_ids=[], group_ids=[group.pk, other.pk],
                              target_kind='threat_feeds', firewall_group_id=scope.pk)
    assert [row['id'] for row in snapshot['groups']] == [group.pk]


def test_configuration_has_no_unscoped_feed_notice(client, feed_setup):
    client.force_login(feed_setup[0])
    response = client.get(reverse('threat_feeds'))
    assert b'legacy' not in response.content.lower()
