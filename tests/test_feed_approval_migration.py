import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_unscoped_feeds_are_removed_preserving_accounts_and_catalog():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    before = [node for node in latest if node[0] not in ('inventory', 'changes')]
    before += [('inventory', '0010_threatfeed_feedaccount'), ('changes', '0005_installationrequest_error_message')]
    try:
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        user = apps.get_model('accounts','User').objects.create(username='legacy-admin')
        entry = apps.get_model('inventory','CatalogEntry').objects.create(name='Legacy IOC', entry_type='group', created_by=user, updated_by=user)
        group = apps.get_model('inventory','AddressGroup').objects.create(entry=entry)
        feed = apps.get_model('inventory','ThreatFeed').objects.create(group=group, slug='legacy_ioc', enabled=True)
        account = apps.get_model('inventory','FeedAccount').objects.create(username='legacy-collector', password='unusable')
        account.feeds.add(feed)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        assert not apps.get_model('inventory','ThreatFeed').objects.filter(pk=feed.pk).exists()
        assert not apps.get_model('inventory','FeedAccount').objects.get(pk=account.pk).feeds.exists()
        assert apps.get_model('inventory','AddressGroup').objects.filter(pk=group.pk).exists()
        assert apps.get_model('inventory','CatalogEntry').objects.filter(pk=entry.pk).exists()
        assert not apps.get_model('inventory','ThreatFeedScope').objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_cleanup_preserves_scoped_content_assignments_and_approval_history():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    before = [node for node in latest if node[0] != 'inventory'] + [('inventory','0012_threatfeedidentity')]
    try:
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        user = apps.get_model('accounts','User').objects.create(username='cleanup-admin')
        fw_group = apps.get_model('firewalls','FirewallGroup').objects.create(name='Preserved firewall group')
        scope = apps.get_model('inventory','ThreatFeedScope').objects.create(firewall_group=fw_group, slug='preserved')
        entry = apps.get_model('inventory','CatalogEntry').objects.create(name='Preserved group', entry_type='group', created_by=user, updated_by=user)
        group = apps.get_model('inventory','AddressGroup').objects.create(entry=entry)
        request = apps.get_model('changes','InstallationRequest').objects.create(requester=user, approver=user,
            self_approved=True, snapshot={'target_kind':'threat_feeds'}, payload_digest='x'*64, idempotency_key='preserved',
            approval_status='APPROVED', execution_status='SUCCEEDED')
        Feed = apps.get_model('inventory','ThreatFeed')
        approved = Feed.objects.create(group=group, scope=scope, slug='approved', revision=3, enabled=True,
                                        approved_request=request, ip_text='192.0.2.1/32\n', domain_text='example.com\n')
        removed = Feed.objects.create(group=group, slug='removed', enabled=False)
        account = apps.get_model('inventory','FeedAccount').objects.create(username='preserved-account', password='existing-hash')
        account.feeds.add(approved, removed)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        current = apps.get_model('inventory','ThreatFeed').objects.get(pk=approved.pk)
        assert current.enabled and current.revision == 3
        assert current.ip_text == '192.0.2.1/32\n' and current.domain_text == 'example.com\n'
        assert current.approved_request_id == request.pk
        assert not apps.get_model('inventory','ThreatFeed').objects.filter(pk=removed.pk).exists()
        assert list(apps.get_model('inventory','FeedAccount').objects.get(pk=account.pk).feeds.values_list('pk',flat=True)) == [approved.pk]
        assert apps.get_model('changes','InstallationRequest').objects.filter(pk=request.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
