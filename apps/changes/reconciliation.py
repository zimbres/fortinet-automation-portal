from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.accounts.permissions import require_capability
from apps.audit.services import record_event
from apps.fortinet.client import FortinetClient
from apps.fortinet.schemas import address_payload
from .models import ChangeRequest, ExecutionStep, ObjectReference
from .executor import safe_state, members


def reconcile_change(*, actor, request_id):
    item = ChangeRequest.objects.select_related('vdom__firewall').get(pk=request_id)
    require_capability(actor,item.vdom,'administer')
    if item.execution_status != 'RECONCILIATION_REQUIRED':
        raise ValidationError('Only uncertain requests can be reconciled.')
    p = item.payload
    with FortinetClient(item.vdom.firewall,item.vdom) as client:
        observed = client.get_address(p['name'])
        if item.operation in ('create_address','edit_address'):
            expected = address_payload(p['name'],p['kind'],p['value'])
            confirmed = bool(observed) and all(observed.get(k) == v for k,v in expected.items())
        elif item.operation == 'delete_address':
            confirmed = observed is None
        else:
            group = client.get_group(p['group'])
            intent = item.steps.filter(step_type='group_intent').order_by('-created_at','-pk').first()
            confirmed = bool(group) and bool(intent) and set(members(group)) == set(members(intent.after_state))
            if p.get('create_new'):
                expected = address_payload(p['name'],p['kind'],p['value'])
                confirmed = confirmed and bool(observed) and all(observed.get(k) == v for k,v in expected.items())
        ExecutionStep.objects.create(request=item,step_type='reconciliation',after_state=safe_state(observed),result='CONFIRMED' if confirmed else 'UNRESOLVED')
    if confirmed:
        if item.operation == 'create_address' or p.get('create_new'):
            ObjectReference.objects.get_or_create(vdom=item.vdom,name=p['name'],defaults={'originating_request':item})
        ChangeRequest.objects.filter(pk=item.pk,execution_status='RECONCILIATION_REQUIRED').update(execution_status='SUCCEEDED',error_message='',finished_at=timezone.now())
    record_event(actor=actor,event_type='change.reconciled',metadata={'request_id':str(item.pk),'status':'confirmed' if confirmed else 'unresolved'})
    item.refresh_from_db()
    return item
