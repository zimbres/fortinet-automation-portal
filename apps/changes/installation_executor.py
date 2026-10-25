"""Preflight and ordered installation on one destination; no network transactions."""
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from apps.audit.services import record_event
from apps.fortinet.client import FortinetClient
from apps.fortinet.capabilities import require_write_capability
from apps.fortinet.exceptions import FortinetError, UncertainResult
from apps.fortinet.schemas import address_payload
from .models import InstallationRequest, InstallationTarget, InstallationStep, InstalledResource, ObjectReference
from .installations import check_installation_authorization
from .executor import heartbeat, safe_state, members, verify_read


def _matches(observed, desired):
    return bool(observed) and all(observed.get(k) == v for k,v in desired.items())


def _connection_identity(target):
    fw = target.vdom.firewall
    return (fw.protocol,fw.hostname,fw.port,target.vdom.name,fw.pk,target.vdom_id,fw.encrypted_token)


def _check_connection_identity(target):
    if _connection_identity(target) != target._execution_connection:
        raise FortinetError('The firewall connection configuration changed during execution. Submit a new installation.')


def _require_capability(target, operation):
    _check_connection_identity(target)
    fw = target.vdom.firewall
    require_write_capability(fw.observed_version, operation,
        (fw.protocol,fw.hostname,fw.port,target.vdom.name))


def preflight_installation(target, client):
    check_installation_authorization(target)
    _check_connection_identity(target)
    fw, snapshot = target.vdom.firewall, target.request.snapshot
    plan = {'addresses': [], 'groups': []}
    for obj in snapshot['objects']:
        name = obj['name']
        if client.get_group(name) is not None:
            raise FortinetError('An address group already uses the requested address name.')
        desired = address_payload(name, obj['kind'], obj['value'])
        before = client.get_address(name)
        if _matches(before, desired):
            action = 'noop'
        else:
            if fw.allowed_namespace and (not name.startswith(fw.allowed_namespace) or name == fw.allowed_namespace):
                raise FortinetError('The address is outside the configured portal namespace.')
            owned = InstalledResource.objects.filter(vdom=target.vdom, resource_type='address', name=name).exists() or ObjectReference.objects.filter(vdom=target.vdom, name=name).exists()
            if before and not owned:
                raise FortinetError('An existing address conflicts with the catalog and is not portal-owned.')
            _require_capability(target, f'install_address_{obj["kind"]}')
            action = 'update' if before else 'create'
        plan['addresses'].append((obj, desired, before, action))
    for group in snapshot['groups']:
        name = group['name']
        if client.get_address(name) is not None:
            raise FortinetError('An address already uses the requested group name.')
        before = client.get_group(name)
        existing = members(before) if before else []
        if before is None: _require_capability(target, 'create_group')
        elif not set(group['members']).issubset(existing): _require_capability(target, 'install_group_members')
        plan['groups'].append((group, before, existing))
    return plan


def _step(target, kind, name, before, after, result, step_type='install'):
    return InstallationStep.objects.create(target=target, resource_type=kind, name=name,
        before_state=safe_state(before), after_state=safe_state(after), result=result, step_type=step_type)


def _before_write(target, owner_id, resource_type, name, operation):
    heartbeat(owner_id)
    check_installation_authorization(target)
    fw = target.vdom.firewall
    if resource_type == 'address':
        if fw.allowed_namespace and (not name.startswith(fw.allowed_namespace) or name == fw.allowed_namespace):
            raise FortinetError('The address is outside the current portal namespace.')
    _require_capability(target, operation)
    if InstallationRequest.objects.filter(pk=target.request_id, recovery_required=True).exists():
        raise UncertainResult('Executor recovery requires read-only reconciliation.')


def _mutate(target, client, plan, owner_id):
    for obj, desired, before, action in plan['addresses']:
        name = obj['name']
        if action == 'noop':
            check_installation_authorization(target)
            _check_connection_identity(target)
            after = client.get_address(name)
            if not _matches(after, desired):
                raise FortinetError('An address changed after preflight. Submit a new installation.')
            _step(target, 'address', name, before, after, 'ALREADY_SATISFIED')
            continue
        # Detect a concurrent administrator changing the preflight state.
        if safe_state(client.get_address(name)) != safe_state(before):
            raise FortinetError('An address changed concurrently. Submit a new installation.')
        _before_write(target, owner_id, 'address', name, f'install_address_{obj["kind"]}')
        _step(target, 'address', name, before, desired, 'PREPARED', 'create' if action == 'create' else 'update')
        if action == 'create': client.create_address(desired)
        else: client.update_address(name, desired)
        after = verify_read(client.get_address, name)
        if not _matches(after, desired): raise UncertainResult('Address installation could not be verified.')
        InstalledResource.objects.update_or_create(vdom=target.vdom, resource_type='address', name=name,
            defaults={'originating_target':target, 'revision':obj['revision']})
        _step(target, 'address', name, before, after, 'SUCCEEDED')
    for group, before, existing in plan['groups']:
        name = group['name']
        current = client.get_group(name)
        if (current is None) != (before is None) or (current and set(members(current)) != set(existing)):
            raise FortinetError('A group changed concurrently. Submit a new installation.')
        desired_members = sorted(set(existing) | set(group['members']))
        desired = {'name':name, 'member':[{'name':x} for x in desired_members]}
        if current is not None and set(desired_members) == set(existing):
            _step(target, 'group', name, before, current, 'ALREADY_SATISFIED')
            continue
        _before_write(target, owner_id, 'group', name, 'create_group' if before is None else 'install_group_members')
        _step(target, 'group', name, before, desired, 'PREPARED', 'create' if before is None else 'update')
        if before is None: client.create_group(desired)
        else: client.set_group_members(name, desired_members)
        after = verify_read(client.get_group, name)
        try: confirmed = after is not None and set(members(after)) == set(desired_members)
        except FortinetError: confirmed = False
        if not confirmed: raise UncertainResult('Group installation could not be verified.')
        if before is None:
            InstalledResource.objects.update_or_create(vdom=target.vdom, resource_type='group', name=name,
                defaults={'originating_target':target,'revision':group['revision']})
        _step(target, 'group', name, before, after, 'SUCCEEDED')


def execute_installation_target(*, target_id, owner_id):
    target = InstallationTarget.objects.select_related('request','vdom__firewall').get(pk=target_id)
    if not InstallationTarget.objects.filter(pk=target_id, execution_status='PENDING').update(execution_status='RUNNING', started_at=timezone.now()):
        return target
    status, error = 'SUCCEEDED', ''
    try:
        heartbeat(owner_id)
        check_installation_authorization(target)
        target._execution_connection = _connection_identity(target)
        with FortinetClient(target.vdom.firewall, target.vdom) as client:
            plan = preflight_installation(target, client)
            _mutate(target, client, plan, owner_id)
    except UncertainResult as exc:
        status, error = 'RECONCILIATION_REQUIRED', str(exc)
    except (FortinetError, PermissionDenied) as exc:
        status, error = 'FAILED', str(exc)
    except Exception:
        status, error = 'RECONCILIATION_REQUIRED', 'Installation stopped unexpectedly. Reconcile observed device state.'
    InstallationTarget.objects.filter(pk=target_id, execution_status='RUNNING').update(execution_status=status, error_message=error[:500], finished_at=timezone.now())
    record_event(actor=None, event_type='installation.target_finished', metadata={'request_id':str(target.request_id),'target_id':target.pk,'status':status})
    target.refresh_from_db()
    return target


def execute_next_installation(*, owner_id):
    from .installations import refresh_installation_status
    item = InstallationRequest.objects.filter(approval_status='APPROVED', execution_status='PENDING', recovery_required=False).order_by('created_at').first()
    if not item or not InstallationRequest.objects.filter(pk=item.pk, approval_status='APPROVED', execution_status='PENDING', recovery_required=False).update(execution_status='RUNNING', started_at=timezone.now()):
        return None
    for target in item.targets.order_by('pk'):
        try:
            heartbeat(owner_id)
        except UncertainResult:
            InstallationRequest.objects.filter(pk=item.pk).update(recovery_required=True)
            break
        if target.execution_status == 'PENDING':
            execute_installation_target(target_id=target.pk, owner_id=owner_id)
    return refresh_installation_status(item.pk)
