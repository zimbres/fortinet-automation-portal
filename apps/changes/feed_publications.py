"""Immutable Threat Feed requests and transactional local publication."""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.permissions import require_catalog_capability, require_group_capability
from apps.audit.services import record_event
from apps.firewalls.models import FirewallGroup
from apps.inventory.models import AddressGroup, ThreatFeed, ThreatFeedIdentity, ThreatFeedScope
from apps.inventory.threat_feeds import require_feed_management
from config.public_url import normalize_public_url
from .approval import require_valid_approval
from .models import InstallationRequest


def require_feed_request_permission(actor, firewall_group_id, capability):
    require_group_capability(actor, firewall_group_id, 'view')
    require_group_capability(actor, firewall_group_id, capability)
    if capability == 'submit':
        require_feed_management(actor)
        require_catalog_capability(actor, 'catalog_view')


def available_slug(name, records):
    base = slugify(name.replace(' ', '_'))[:90] or 'group'
    slug, suffix = base, 2
    while records.filter(slug=slug).exists():
        slug = f'{base}_{suffix}'
        suffix += 1
    return slug


def scope_slug(firewall_group):
    current = ThreatFeedScope.objects.filter(firewall_group=firewall_group).first()
    return current.slug if current else available_slug(firewall_group.name, ThreatFeedScope.objects.all())


def prepare_feed_scope(*, actor, firewall_group_id):
    require_feed_request_permission(actor, firewall_group_id, 'submit')
    firewall_group = FirewallGroup.objects.get(pk=firewall_group_id)
    scope, _ = ThreatFeedScope.objects.get_or_create(firewall_group=firewall_group,
                                                    defaults={'slug':scope_slug(firewall_group)})
    return scope


def build_feed_snapshot(*, actor, object_ids, group_ids, firewall_group_id):
    require_feed_request_permission(actor, firewall_group_id, 'submit')
    if object_ids or not group_ids:
        raise ValidationError('Threat Feeds requires address groups only. Clear standalone objects and select at least one address group.')
    firewall_group = FirewallGroup.objects.get(pk=firewall_group_id)
    groups = list(AddressGroup.objects.filter(pk__in=set(group_ids)).select_related('entry').prefetch_related('members__entry'))
    if len(groups) != len(set(group_ids)):
        raise ValidationError('Select existing address groups.')
    namespace = ThreatFeedScope.objects.filter(firewall_group=firewall_group).first()
    namespace_slug = scope_slug(firewall_group)
    definitions, snapshots = {}, []
    existing = ThreatFeed.objects.filter(scope=namespace) if namespace else ThreatFeed.objects.none()
    identities = ThreatFeedIdentity.objects.filter(scope=namespace) if namespace else ThreatFeedIdentity.objects.none()
    reserved = set(existing.values_list('slug', flat=True)) | set(identities.values_list('slug', flat=True))
    for group in sorted(groups, key=lambda row:row.pk):
        members = list(group.members.all())
        current = existing.filter(group=group).first()
        identity = identities.filter(group=group).first()
        slug = current.slug if current else identity.slug if identity else available_slug(group.entry.name, existing)
        base, suffix = slug, 2
        while not (current or identity) and slug in reserved:
            slug = f'{base}_{suffix}'
            suffix += 1
        reserved.add(slug)
        lines = lambda kinds: ''.join(value + '\n' for value in sorted({m.value for m in members if m.kind in kinds}))
        ip_text, domain_text = lines({'subnet'}), lines({'fqdn', 'wildcard_fqdn'})
        old_ips = set(current.ip_text.splitlines()) if current else set()
        old_domains = set(current.domain_text.splitlines()) if current else set()
        new_ips, new_domains = set(ip_text.splitlines()), set(domain_text.splitlines())
        changes = {'ip_added':sorted(new_ips - old_ips), 'ip_removed':sorted(old_ips - new_ips),
                   'domain_added':sorted(new_domains - old_domains), 'domain_removed':sorted(old_domains - new_domains),
                   'enable':not current or not current.enabled}
        if not any(changes.values()):
            continue
        definitions.update({member.pk:member for member in members})
        snapshots.append({'id':group.pk, 'entry_id':group.entry_id, 'name':group.entry.name,
                          'revision':group.entry.revision, 'members':sorted(m.entry.name for m in members),
                          'slug':slug, 'base_id':current.pk if current else None,
                          'base_revision':current.revision if current else 0,
                          'ip_text':ip_text, 'domain_text':domain_text, 'changes':changes})
    if not snapshots:
        raise ValidationError('No changes to publish for the selected feeds.')
    return {'target_kind':'threat_feeds', 'firewall_group_id':firewall_group.pk,
            'firewall_group_name':firewall_group.name, 'firewall_group_slug':namespace_slug,
            'objects':[{'id':obj.pk, 'entry_id':obj.entry_id, 'name':obj.entry.name, 'revision':obj.entry.revision,
                        'kind':obj.kind, 'value':obj.value} for obj in sorted(definitions.values(), key=lambda row:row.pk)],
            'groups':snapshots, 'destinations':[]}


def reserve_feed_identities(snapshot):
    scope = ThreatFeedScope.objects.get(firewall_group_id=snapshot['firewall_group_id'])
    try:
        with transaction.atomic():
            for group in snapshot['groups']:
                identity, _ = ThreatFeedIdentity.objects.get_or_create(scope=scope, group_id=group['id'],
                                                                     defaults={'slug':group['slug']})
                if identity.slug != group['slug']:
                    raise ValidationError('A feed URL reservation changed. Preview and submit again.')
    except IntegrityError:
        raise ValidationError('A feed URL was reserved concurrently. Preview and submit again.') from None


def feed_snapshot_urls(snapshot):
    """Presentation only: never store a deployment URL in approved intent."""
    base = normalize_public_url(settings.APP_PUBLIC_URL)
    return [{'name':group['name'], 'ip_text':group['ip_text'], 'domain_text':group['domain_text'],
             'changes':group.get('changes'), 'is_update':group['base_id'] is not None,
             'ip_count':len(group['ip_text'].splitlines()), 'domain_count':len(group['domain_text'].splitlines()),
             'base_revision':group['base_revision'],
             'ip_url':f"{base}/threat-feeds/{snapshot['firewall_group_slug']}/{group['slug']}/ip_list.txt",
             'domain_url':f"{base}/threat-feeds/{snapshot['firewall_group_slug']}/{group['slug']}/domain_list.txt"}
            for group in snapshot['groups']]


def execute_feed_request(*, request_id, owner_id):
    from .executor import heartbeat
    from .installations import verify_installation_intent
    from apps.fortinet.exceptions import FortinetError
    try:
        with transaction.atomic():
            heartbeat(owner_id)
            item = InstallationRequest.objects.select_for_update().select_related('requester','approver').get(pk=request_id)
            if item.execution_status == 'SUCCEEDED':
                return item
            if item.snapshot.get('target_kind') != 'threat_feeds' or item.execution_status != 'RUNNING':
                raise ValidationError('This request is not awaiting feed publication.')
            verify_installation_intent(item)
            require_valid_approval(item)
            require_feed_request_permission(item.requester, item.snapshot['firewall_group_id'], 'submit')
            require_feed_request_permission(item.approver, item.snapshot['firewall_group_id'], 'approve')
            scope = ThreatFeedScope.objects.get(firewall_group_id=item.snapshot['firewall_group_id'])
            if scope.slug != item.snapshot['firewall_group_slug']:
                raise ValidationError('The approved feed namespace changed. Submit a new request.')
            for group in item.snapshot['groups']:
                current = ThreatFeed.objects.filter(scope=scope, group_id=group['id']).first()
                if ((current.pk if current else None) != group['base_id'] or
                        (current.revision if current else 0) != group['base_revision']):
                    raise ValidationError('A publication changed after submission. Submit a new Threat Feeds request.')
                if not AddressGroup.objects.filter(pk=group['id'], entry_id=group['entry_id']).exists():
                    raise ValidationError('A submitted address group no longer exists.')
                feed = current or ThreatFeed(scope=scope, group_id=group['id'], slug=group['slug'])
                if feed.slug != group['slug']:
                    raise ValidationError('The approved feed URL changed. Submit a new request.')
                feed.ip_text, feed.domain_text = group['ip_text'], group['domain_text']
                feed.revision = group['base_revision'] + 1
                feed.enabled, feed.approved_request = True, item
                feed.save()
                record_event(actor=item.approver, event_type='threat_feed.published', metadata={
                    'request_id':str(item.pk), 'target_id':feed.pk, 'group_id':scope.firewall_group_id,
                    'entry_id':group['entry_id'], 'count':feed.revision,
                })
            InstallationRequest.objects.filter(pk=item.pk).update(execution_status='SUCCEEDED', finished_at=timezone.now(), error_message='')
            record_event(actor=None, event_type='installation.feed_finished', metadata={'request_id':str(item.pk),'status':'SUCCEEDED'})
    except OperationalError:
        raise  # Let the runner recover the rolled-back local transaction.
    except (PermissionDenied, ValidationError, FortinetError) as exc:
        error = ' '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        InstallationRequest.objects.filter(pk=request_id).update(execution_status='FAILED', finished_at=timezone.now(), error_message=error[:500])
        record_event(actor=None, event_type='installation.feed_finished', metadata={'request_id':str(request_id),'status':'FAILED'})
    except Exception:
        # All local publication writes rolled back; no device reconciliation is necessary.
        InstallationRequest.objects.filter(pk=request_id).update(execution_status='FAILED', finished_at=timezone.now(),
                                                                 error_message='Publication rolled back. Submit a new request.')
        record_event(actor=None, event_type='installation.feed_finished', metadata={'request_id':str(request_id),'status':'FAILED'})
    return InstallationRequest.objects.get(pk=request_id)
