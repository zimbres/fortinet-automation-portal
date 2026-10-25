from .approval import require_valid_approval
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.accounts.permissions import require_capability
from apps.audit.services import record_event
from apps.fortinet.client import FortinetClient
from apps.fortinet.capabilities import require_write_capability
from apps.fortinet.exceptions import FortinetError, UncertainResult
from apps.fortinet.schemas import address_payload
from .models import ChangeRequest, ExecutorLease, ExecutionStep, ObjectReference
from .services import digest_intent


def _mark_interrupted_execution():
    ChangeRequest.objects.filter(execution_status='RUNNING').update(
        execution_status='RECONCILIATION_REQUIRED', error_message='Executor interrupted. Read-only reconciliation is required.')
    from .models import InstallationRequest, InstallationTarget
    interrupted = InstallationRequest.objects.filter(execution_status='RUNNING')
    InstallationTarget.objects.filter(request__in=interrupted, execution_status='RUNNING').update(
        execution_status='RECONCILIATION_REQUIRED', error_message='Executor interrupted. Read-only reconciliation is required.')
    interrupted.update(execution_status='RECONCILIATION_REQUIRED', recovery_required=True)


@transaction.atomic
def recover_locked_execution(*, owner_id):
    # A command-level lock can occur after a claim or even after a device write.
    # Once SQLite is available, reconcile interrupted work rather than replay it.
    if ExecutorLease.objects.filter(pk=1,owner=owner_id,expires_at__gt=timezone.now()).exists():
        _mark_interrupted_execution()


@transaction.atomic
def acquire_lease(owner_id):
    now = timezone.now()
    lease, _ = ExecutorLease.objects.get_or_create(pk=1, defaults={'owner':owner_id, 'expires_at':now})
    if lease.owner != owner_id and lease.expires_at > now:
        raise FortinetError('Another executor owns the execution lease.')
    if lease.expires_at <= now:
        _mark_interrupted_execution()
    if not ExecutorLease.objects.filter(pk=1).filter(
        owner=lease.owner, expires_at=lease.expires_at
    ).update(owner=owner_id, expires_at=now+timedelta(minutes=5)):
        raise FortinetError('Executor ownership changed.')


def heartbeat(owner_id):
    now = timezone.now()
    if not ExecutorLease.objects.filter(pk=1, owner=owner_id, expires_at__gt=now).update(expires_at=now+timedelta(minutes=5)):
        raise UncertainResult('Executor ownership was lost.')


def check_authorization(item):
    require_capability(item.requester, item.vdom, 'submit')
    require_valid_approval(item)
    require_capability(item.approver, item.vdom, 'approve')
    if item.payload_digest != digest_intent(item.vdom_id, item.operation, item.payload):
        raise PermissionDenied('Approved intent no longer matches the request.')


def safe_state(record):
    if not record:
        return {}
    return {key:record[key] for key in ('name','type','subnet','fqdn','member') if key in record}


def members(record):
    value = record.get('member', [])
    if not isinstance(value, list) or not all(isinstance(x,dict) and isinstance(x.get('name'),str) for x in value):
        raise FortinetError('Unsupported group membership response.')
    return [x['name'] for x in value]


def verify_read(call, *args):
    try:
        return call(*args)
    except FortinetError:
        raise UncertainResult('The write was sent but the resulting state could not be read back.') from None


def mutate(item, client, owner_id):
    p, fw, op = item.payload, item.vdom.firewall, item.operation
    name = p['name']
    creates = op == 'create_address' or (op == 'add_group_member' and p.get('create_new'))
    if op in ('create_address','edit_address','delete_address') or creates:
        if fw.allowed_namespace and (not name.startswith(fw.allowed_namespace) or name == fw.allowed_namespace):
            raise FortinetError('The object is outside the configured portal namespace.')
    if op in ('edit_address','delete_address') and not ObjectReference.objects.filter(vdom=item.vdom,name=name).exists():
        raise FortinetError('This object is not owned by the portal.')
    group = None
    if op in ('add_group_member','remove_group_member'):
        group = client.get_group(p['group'])
        if not group:
            raise FortinetError('The selected group does not exist.')
        existing = members(group)
    before = client.get_address(name)
    desired = address_payload(name,p['kind'],p['value']) if creates or op == 'edit_address' else None

    def before_write():
        heartbeat(owner_id)
        item.refresh_from_db()
        check_authorization(item)

    if creates:
        if before is not None:
            raise FortinetError('The address already exists. Select the existing-object workflow.')
        before_write()
        client.create_address(desired)
        after = verify_read(client.get_address,name)
        if not after or any(after.get(k) != v for k,v in desired.items()):
            raise UncertainResult('Created address could not be verified.')
        ObjectReference.objects.get_or_create(vdom=item.vdom,name=name,defaults={'originating_request':item})
        ExecutionStep.objects.create(request=item,step_type='create_address',after_state=safe_state(after),result='SUCCEEDED')
    elif before is None:
        raise FortinetError('The selected address does not exist.')
    if op == 'edit_address':
        before_write()
        client.update_address(name, desired)
        after = verify_read(client.get_address,name)
        if not after or any(after.get(k) != v for k,v in desired.items()):
            raise UncertainResult('Updated address could not be verified.')
        ExecutionStep.objects.create(request=item,step_type=op,before_state=safe_state(before),after_state=safe_state(after),result='SUCCEEDED')
    elif op == 'delete_address':
        report = client.get_reference_report(name)
        if not report.complete or report.references:
            raise FortinetError('Deletion blocked: references are present or reference inspection is incomplete.')
        before_write()
        client.delete_address(name)
        if verify_read(client.get_address,name) is not None:
            raise UncertainResult('Address deletion could not be verified.')
        ExecutionStep.objects.create(request=item,step_type=op,before_state=safe_state(before),result='SUCCEEDED')
    elif op in ('add_group_member','remove_group_member'):
        group_name = p['group']
        desired_members = list(dict.fromkeys(existing + [name])) if op == 'add_group_member' else [x for x in existing if x != name]
        ExecutionStep.objects.create(request=item,step_type='group_intent',before_state=safe_state(group),
            after_state={'name':group_name,'member':[{'name':x} for x in desired_members]},result='PREPARED')
        if existing != desired_members:
            current = client.get_group(group_name)
            if not current or members(current) != existing:
                raise FortinetError('The group changed concurrently. Submit a new request.')
            before_write()
            client.set_group_members(group_name, desired_members)
        after = verify_read(client.get_group,group_name)
        try:
            confirmed_members = members(after) if after else None
        except FortinetError:
            raise UncertainResult('The group response could not be interpreted after the write.') from None
        if confirmed_members is None or set(confirmed_members) != set(desired_members):
            raise UncertainResult('Group membership could not be verified.')
        ExecutionStep.objects.create(request=item,step_type=op,before_state=safe_state(group),after_state=safe_state(after),result='SUCCEEDED')


def execute_legacy_next(*, owner_id: str):
    acquire_lease(owner_id)
    item = ChangeRequest.objects.filter(approval_status='APPROVED', execution_status='PENDING').order_by('created_at').first()
    if not item:
        return None
    if not ChangeRequest.objects.filter(pk=item.pk,approval_status='APPROVED',execution_status='PENDING').update(execution_status='RUNNING',started_at=timezone.now()):
        return None
    item = ChangeRequest.objects.select_related('requester','approver','vdom__firewall').get(pk=item.pk)
    status, error = 'SUCCEEDED', ''
    try:
        check_authorization(item)
        require_write_capability(item.vdom.firewall.observed_version, item.operation)
        with FortinetClient(item.vdom.firewall,item.vdom) as client:
            mutate(item,client,owner_id)
    except UncertainResult as exc:
        status, error = 'RECONCILIATION_REQUIRED', str(exc)
    except (FortinetError, PermissionDenied) as exc:
        status, error = 'FAILED', str(exc)
    except Exception:
        status, error = 'RECONCILIATION_REQUIRED', 'Execution stopped unexpectedly. Inspect the observed firewall state before further action.'
    ChangeRequest.objects.filter(pk=item.pk,execution_status='RUNNING').update(execution_status=status,error_message=error,finished_at=timezone.now())
    record_event(actor=None,event_type='change.execution_finished',metadata={'request_id':str(item.pk),'status':status})
    item.refresh_from_db()
    return item


def execute_next(*, owner_id: str):
    from .models import InstallationRequest
    from .installation_executor import execute_next_installation
    acquire_lease(owner_id)
    legacy = ChangeRequest.objects.filter(approval_status='APPROVED', execution_status='PENDING').order_by('created_at').first()
    installation = InstallationRequest.objects.filter(approval_status='APPROVED', execution_status='PENDING', recovery_required=False).order_by('created_at').first()
    if installation and (not legacy or installation.created_at < legacy.created_at):
        return execute_next_installation(owner_id=owner_id)
    return execute_legacy_next(owner_id=owner_id) if legacy else None
