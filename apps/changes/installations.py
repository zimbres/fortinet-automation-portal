"""Immutable catalog snapshots, all-destination approval and status aggregation."""
import hashlib
import json
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.accounts.permissions import require_capability, require_catalog_capability, visible_vdoms, require_group_capability, can_self_approve
from apps.audit.services import record_event
from apps.firewalls.groups import resolve_destinations
from apps.firewalls.models import FirewallGroup
from apps.inventory.models import AddressObject, AddressGroup, CatalogEntry
from .models import InstallationRequest, InstallationTarget
from .approval import require_valid_approval


def installation_digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build_snapshot(*, actor, object_ids, group_ids, target_kind, vdom_id=None, firewall_group_id=None):
    require_catalog_capability(actor, 'catalog_view')
    scopes = resolve_destinations(actor=actor, target_kind=target_kind, vdom_id=vdom_id, firewall_group_id=firewall_group_id)
    objects = list(AddressObject.objects.filter(pk__in=set(object_ids)).select_related('entry'))
    groups = list(AddressGroup.objects.filter(pk__in=set(group_ids)).select_related('entry').prefetch_related('members__entry'))
    if len(objects) != len(set(object_ids)) or len(groups) != len(set(group_ids)) or not (objects or groups):
        raise ValidationError('Select existing catalog objects or address groups.')
    definitions = {x.pk: x for x in objects}
    for group in groups:
        definitions.update({x.pk: x for x in group.members.all()})
    return {'target_kind': target_kind, 'firewall_group_id': firewall_group_id,
            'firewall_group_name': FirewallGroup.objects.get(pk=firewall_group_id).name if firewall_group_id else None,
            'objects': [{'id': x.pk, 'entry_id': x.entry_id, 'name': x.entry.name, 'revision': x.entry.revision, 'kind': x.kind, 'value': x.value} for x in sorted(definitions.values(), key=lambda x:x.entry.name)],
            'groups': [{'id': x.pk, 'entry_id': x.entry_id, 'name': x.entry.name, 'revision': x.entry.revision, 'members': sorted(m.entry.name for m in x.members.all())} for x in sorted(groups, key=lambda x:x.entry.name)],
            'destinations': [{'vdom_id': x.pk, 'firewall_id': x.firewall_id, 'firewall': x.firewall.name, 'vdom': x.name} for x in scopes]}


@transaction.atomic
def submit_installation(*, actor, object_ids, group_ids, target_kind, idempotency_key, vdom_id=None, firewall_group_id=None):
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValidationError('A valid submission key is required.')
    snapshot = build_snapshot(actor=actor, object_ids=object_ids, group_ids=group_ids, target_kind=target_kind, vdom_id=vdom_id, firewall_group_id=firewall_group_id)
    for definition in snapshot['objects'] + snapshot['groups']:
        if not CatalogEntry.objects.filter(pk=definition['entry_id'], revision=definition['revision']).exists():
            raise ValidationError('The catalog changed during submission. Preview again.')
    digest = installation_digest(snapshot)
    existing = InstallationRequest.objects.filter(requester=actor, idempotency_key=idempotency_key).first()
    if existing:
        if existing.payload_digest != digest:
            raise ValidationError('This submission key identifies a different installation.')
        return existing
    item = InstallationRequest.objects.create(requester=actor, snapshot=snapshot, payload_digest=digest, idempotency_key=idempotency_key)
    InstallationTarget.objects.bulk_create([InstallationTarget(request=item, vdom_id=x['vdom_id'], destination=x) for x in snapshot['destinations']])
    record_event(actor=actor, event_type='installation.submitted', metadata={'request_id': str(item.pk)})
    return item


def installations_for(user, capability='view'):
    from apps.firewalls.groups import visible_firewall_groups
    groups=visible_firewall_groups(user,capability)
    allowed=visible_vdoms(user,capability).filter(pk__in=visible_vdoms(user,'view'))
    hidden=InstallationTarget.objects.exclude(vdom__in=allowed).values('request_id')
    return InstallationRequest.objects.filter(snapshot__firewall_group_id__in=groups.values_list('pk',flat=True)).exclude(pk__in=hidden).distinct()


def require_installation_group(user,item,capability):
    group_id=item.snapshot.get('firewall_group_id')
    if item.snapshot.get('target_kind') != 'firewall_group' or not group_id:
        raise PermissionDenied('This historical request has no authorized firewall group. Submit a new group request.')
    require_group_capability(user,group_id,'view')
    require_group_capability(user,group_id,capability)
    from apps.firewalls.models import FirewallGroupMember
    current=set(FirewallGroupMember.objects.filter(group_id=group_id).values_list('vdom_id',flat=True))
    if not {x['vdom_id'] for x in item.snapshot['destinations']}.issubset(current):
        raise PermissionDenied('A submitted destination is no longer a member of the request group.')


def verify_installation_intent(item):
    if item.payload_digest != installation_digest(item.snapshot):
        raise PermissionDenied('Approved installation intent changed.')
    expected = {x['vdom_id']:x for x in item.snapshot['destinations']}
    targets = list(item.targets.all())
    if len(targets) != len(expected) or any(expected.get(x.vdom_id) != x.destination for x in targets):
        raise PermissionDenied('Approved installation destinations changed.')


def check_installation_authorization(target):
    from apps.firewalls.models import VDOM
    current_vdom = VDOM.objects.select_related('firewall').get(pk=target.vdom_id)
    target.vdom = current_vdom
    item = InstallationRequest.objects.select_related('requester','approver').get(pk=target.request_id)
    verify_installation_intent(item)
    require_valid_approval(item)
    require_installation_group(item.requester,item,'submit')
    require_installation_group(item.approver,item,'approve')
    # Catalog edits/deletion do not revoke submitted snapshots; destination rights still apply.
    require_capability(item.requester, target.vdom, 'submit')
    require_capability(item.approver, target.vdom, 'approve')
    require_capability(item.requester, target.vdom, 'view')
    require_capability(item.approver, target.vdom, 'view')


@transaction.atomic
def decide_installation(*, actor, request_id, status):
    item = InstallationRequest.objects.get(pk=request_id)
    if status not in ('APPROVED', 'REJECTED', 'CANCELLED'):
        raise ValidationError('Unknown decision.')
    verify_installation_intent(item)
    allowed_approval = ('PENDING','APPROVED') if status == 'CANCELLED' else ('PENDING',)
    if item.approval_status not in allowed_approval or item.execution_status != 'PENDING' or item.started_at or item.targets.exclude(execution_status='PENDING').exists():
        raise ValidationError('This installation is no longer awaiting a decision.')
    if status == 'CANCELLED':
        if actor.pk != item.requester_id:
            raise PermissionDenied('Only the requester may cancel.')
    elif actor.pk == item.requester_id and not (status == 'APPROVED' and can_self_approve(actor)):
        raise PermissionDenied('You cannot approve or reject your own installation.')
    require_installation_group(actor,item,'submit' if status == 'CANCELLED' else 'approve')
    if status == 'APPROVED':
        require_installation_group(item.requester,item,'submit')
    for target in item.targets.select_related('vdom__firewall'):
        require_capability(actor, target.vdom, 'view')
        require_capability(actor, target.vdom, 'submit' if status == 'CANCELLED' else 'approve')
        if status == 'APPROVED': require_capability(item.requester, target.vdom, 'submit')
    updates = {'approval_status': status}
    if status == 'APPROVED': updates.update(approver=actor, approved_at=timezone.now(),self_approved=actor.pk == item.requester_id)
    if status == 'CANCELLED': updates.update(execution_status='CANCELLED',finished_at=timezone.now())
    if not InstallationRequest.objects.filter(pk=item.pk, approval_status__in=allowed_approval, execution_status='PENDING',started_at__isnull=True).update(**updates):
        raise ValidationError('This installation already has a decision.')
    if status == 'CANCELLED':
        item.targets.filter(execution_status='PENDING').update(execution_status='CANCELLED',finished_at=updates['finished_at'])
    metadata={'request_id':str(item.pk)}
    if status == 'APPROVED': metadata['self_approved']=updates['self_approved']
    record_event(actor=actor,event_type=f'installation.{status.lower()}',metadata=metadata)
    item.refresh_from_db()
    return item


def refresh_installation_status(request_id):
    item = InstallationRequest.objects.get(pk=request_id)
    states = set(item.targets.values_list('execution_status', flat=True))
    if item.approval_status == 'CANCELLED': status = 'CANCELLED'
    elif item.recovery_required: status = 'RECONCILIATION_REQUIRED'
    elif 'RUNNING' in states: status = 'RUNNING'
    elif 'RECONCILIATION_REQUIRED' in states: status = 'RECONCILIATION_REQUIRED'
    elif states == {'SUCCEEDED'}: status = 'SUCCEEDED'
    elif states == {'FAILED'}: status = 'FAILED'
    elif 'PENDING' in states: status = 'RUNNING' if item.started_at else 'PENDING'
    else: status = 'PARTIALLY_SUCCEEDED'
    InstallationRequest.objects.filter(pk=request_id).update(execution_status=status, finished_at=timezone.now() if status in ('SUCCEEDED','FAILED','PARTIALLY_SUCCEEDED','CANCELLED') else None)
    item.refresh_from_db()
    return item
