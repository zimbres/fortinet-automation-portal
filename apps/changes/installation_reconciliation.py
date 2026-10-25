"""Read-only installation recovery. Never replay an uncertain mutation."""
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.accounts.permissions import require_capability
from apps.audit.services import record_event
from apps.fortinet.client import FortinetClient
from apps.fortinet.schemas import address_payload
from apps.fortinet.exceptions import FortinetError
from .executor import members, safe_state
from .models import InstallationRequest, InstallationTarget, InstallationStep, InstalledResource
from .installations import require_installation_group, verify_installation_intent, refresh_installation_status


def reconcile_installation(*, actor, request_id):
    item = InstallationRequest.objects.get(pk=request_id)
    verify_installation_intent(item)
    require_installation_group(actor,item,'administer')
    targets = list(item.targets.select_related('vdom__firewall'))
    for target in targets: require_capability(actor, target.vdom, 'administer')
    if item.execution_status != 'RECONCILIATION_REQUIRED' and not item.targets.filter(execution_status='RECONCILIATION_REQUIRED').exists():
        raise ValidationError('Only uncertain installations can be reconciled.')
    for target in targets:
        if target.execution_status != 'RECONCILIATION_REQUIRED': continue
        confirmed = True
        observed_states = []
        try:
            with FortinetClient(target.vdom.firewall, target.vdom) as client:
                for obj in item.snapshot['objects']:
                    observed = client.get_address(obj['name'])
                    desired = address_payload(obj['name'], obj['kind'], obj['value'])
                    confirmed = confirmed and bool(observed) and all(observed.get(k) == v for k,v in desired.items())
                    observed_states.append(('address', obj, observed))
                for group in item.snapshot['groups']:
                    observed = client.get_group(group['name'])
                    prepared = target.steps.filter(resource_type='group', name=group['name'], result='PREPARED').order_by('-pk').first()
                    expected = set(members(prepared.after_state)) if prepared else set(group['members'])
                    confirmed = confirmed and observed is not None and expected.issubset(set(members(observed)))
                    observed_states.append(('group', group, observed))
        except FortinetError:
            confirmed = False
        with transaction.atomic():
            for kind, definition, observed in observed_states:
                InstallationStep.objects.create(target=target, step_type='reconciliation', resource_type=kind, name=definition['name'], after_state=safe_state(observed), result='CONFIRMED' if confirmed else 'UNRESOLVED')
                if confirmed and target.steps.filter(resource_type=kind, name=definition['name'], step_type='create', result='PREPARED').exists():
                    InstalledResource.objects.update_or_create(vdom=target.vdom, resource_type=kind, name=definition['name'], defaults={'originating_target':target, 'revision':definition['revision']})
            if confirmed:
                InstallationTarget.objects.filter(pk=target.pk, execution_status='RECONCILIATION_REQUIRED').update(execution_status='SUCCEEDED', error_message='')
    if not item.targets.filter(execution_status__in=['RUNNING','RECONCILIATION_REQUIRED']).exists():
        InstallationRequest.objects.filter(pk=item.pk).update(recovery_required=False)
        # Only untouched targets can resume; completed targets retain their history.
        if item.targets.filter(execution_status='PENDING').exists():
            InstallationRequest.objects.filter(pk=item.pk).update(execution_status='PENDING')
            item.refresh_from_db()
            return item
    record_event(actor=actor, event_type='installation.reconciled', metadata={'request_id':str(item.pk)})
    return refresh_installation_status(item.pk)
