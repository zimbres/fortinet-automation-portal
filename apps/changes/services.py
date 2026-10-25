import hashlib
import json
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.accounts.permissions import require_capability, can_self_approve
from apps.audit.services import record_event
from apps.fortinet.schemas import address_payload, validate_name
from .models import ChangeRequest, OPERATIONS


def digest_intent(vdom_id, operation, payload):
    return hashlib.sha256(json.dumps([vdom_id,operation,payload], sort_keys=True, separators=(',',':')).encode()).hexdigest()


def normalize_payload(operation, payload):
    if operation not in OPERATIONS:
        raise ValidationError('Unknown operation.')
    normalized = {'name': validate_name(payload.get('name', ''))}
    if operation in ['create_address','edit_address'] or (operation == 'add_group_member' and payload.get('create_new')):
        address_payload(normalized['name'], payload.get('kind'), payload.get('value',''))
        normalized.update(kind=payload['kind'], value=payload['value'].strip())
    if operation in ['add_group_member','remove_group_member']:
        normalized['group'] = validate_name(payload.get('group',''))
        normalized['create_new'] = bool(payload.get('create_new',False)) if operation == 'add_group_member' else False
    return normalized


@transaction.atomic
def submit_change(*, actor, vdom, operation: str, payload: dict, idempotency_key: str) -> ChangeRequest:
    raise ValidationError('New requests must target a firewall group through installation.')


@transaction.atomic
def transition(*, actor, request_id, status):
    item = ChangeRequest.objects.select_related('vdom__firewall').get(pk=request_id)
    if status == 'CANCELLED':
        require_capability(actor, item.vdom, 'submit')
        if item.requester_id != actor.pk:
            raise PermissionDenied('Only the requester can cancel this request.')
    else:
        require_capability(actor, item.vdom, 'approve')
        if actor.pk == item.requester_id and not (status == 'APPROVED' and can_self_approve(actor)):
            raise PermissionDenied('You cannot approve or reject your own request.')
    updates = {'approval_status': status}
    if status == 'APPROVED':
        require_capability(item.requester, item.vdom, 'submit')
        updates.update(approver=actor, approved_at=timezone.now(),self_approved=actor.pk == item.requester_id)
    allowed_approval=('PENDING','APPROVED') if status == 'CANCELLED' else ('PENDING',)
    if status == 'CANCELLED': updates.update(execution_status='CANCELLED',finished_at=timezone.now())
    if not ChangeRequest.objects.filter(pk=item.pk, approval_status__in=allowed_approval, execution_status='PENDING',started_at__isnull=True).update(**updates):
        raise ValidationError('This request is no longer awaiting a decision.')
    metadata={'request_id':str(item.pk)}
    if status == 'APPROVED': metadata['self_approved']=updates['self_approved']
    record_event(actor=actor,event_type=f'change.{status.lower()}',metadata=metadata)
    item.refresh_from_db()
    return item


def approve_change(*, actor, request_id): return transition(actor=actor, request_id=request_id, status='APPROVED')
def reject_change(*, actor, request_id, reason=''): return transition(actor=actor, request_id=request_id, status='REJECTED')
def cancel_change(*, actor, request_id): return transition(actor=actor, request_id=request_id, status='CANCELLED')
