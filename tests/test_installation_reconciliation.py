from tests.group_helpers import group_for
from datetime import timedelta
import pytest
from django.utils import timezone
from tests.test_catalog import manager
from tests.test_installations import installation
from tests.test_installation_execution import device

pytestmark = pytest.mark.django_db


def test_scheduler_runs_installation_once(installation, device):
    from apps.changes.executor import execute_next
    item = execute_next(owner_id='worker')
    assert item.pk == installation[0].pk
    assert item.execution_status == 'SUCCEEDED'
    count = len(device['calls'])
    assert execute_next(owner_id='worker') is None
    assert len(device['calls']) == count


def test_restart_between_targets_does_not_replay(installation, device, scope):
    from apps.changes.models import InstallationRequest, ExecutorLease
    from apps.changes.executor import acquire_lease
    InstallationRequest.objects.filter(pk=installation[0].pk).update(execution_status='RUNNING', started_at=timezone.now())
    ExecutorLease.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
    acquire_lease('replacement')
    installation[0].refresh_from_db()
    assert installation[0].recovery_required
    assert installation[0].execution_status == 'RECONCILIATION_REQUIRED'
    assert not device['calls']


def test_read_only_reconciliation(installation, device, scope):
    from apps.changes.installation_executor import execute_installation_target
    from apps.changes.installation_reconciliation import reconcile_installation
    from apps.accounts.models import GroupGrant
    GroupGrant.objects.create(user=scope[1], firewall_group=group_for(scope[2]), capability='administer')
    device['mode'] = 'bad_read'
    target = execute_installation_target(target_id=installation[0].targets.get().pk, owner_id='worker')
    assert target.execution_status == 'RECONCILIATION_REQUIRED'
    device['mode'] = 'success'
    # The address exists, but the group write was never reached: unresolved.
    before = len([m for m,p in device['calls'] if m != 'GET'])
    result = reconcile_installation(actor=scope[1], request_id=installation[0].pk)
    assert result.execution_status == 'RECONCILIATION_REQUIRED'
    assert len([m for m,p in device['calls'] if m != 'GET']) == before


def test_parent_aggregate_partial_and_uncertain(installation):
    from apps.changes.models import InstallationTarget
    from apps.changes.installations import refresh_installation_status
    from apps.firewalls.models import Firewall, VDOM
    item = installation[0]
    item.targets.update(execution_status='SUCCEEDED')
    vd = VDOM.objects.create(firewall=Firewall.objects.create(name='Other',hostname='192.0.2.2'),name='root')
    t = InstallationTarget.objects.create(request=item,vdom=vd,destination={},execution_status='FAILED')
    assert refresh_installation_status(item.pk).execution_status == 'PARTIALLY_SUCCEEDED'
    t.execution_status = 'RECONCILIATION_REQUIRED'
    t.save()
    assert refresh_installation_status(item.pk).execution_status == 'RECONCILIATION_REQUIRED'


def test_complete_first_target_crash_reconcile_then_continue(installation, device, scope):
    from apps.changes.models import InstallationRequest, InstallationTarget, ExecutorLease
    from apps.changes.executor import acquire_lease, execute_next
    from apps.changes.installation_executor import execute_installation_target
    from apps.changes.installation_reconciliation import reconcile_installation
    from apps.firewalls.models import Firewall, VDOM
    from apps.accounts.models import GroupGrant
    from apps.changes.installations import installation_digest
    item = installation[0]
    first = execute_installation_target(target_id=item.targets.get().pk,owner_id='worker')
    assert first.execution_status == 'SUCCEEDED'
    second_fw = Firewall.objects.create(name='Other',hostname='192.0.2.2',allowed_namespace='portal_')
    second = VDOM.objects.create(firewall=second_fw,name='root')
    second_fw.set_token('test-secret'); second_fw.save()
    for user,caps in [(scope[0],['view','submit']), (scope[1],['view','approve','administer'])]:
        for cap in caps: GroupGrant.objects.create(user=user,firewall_group=group_for(second),capability=cap)
    GroupGrant.objects.create(user=scope[1],firewall_group=group_for(scope[2]),capability='administer')
    from apps.firewalls.models import FirewallGroupMember
    FirewallGroupMember.objects.create(group_id=item.snapshot['firewall_group_id'],firewall=second_fw,vdom=second)
    # Assemble a valid two-target intent to model a crash after the first target.
    destination={'vdom_id':second.pk,'firewall_id':second_fw.pk,'firewall':second_fw.name,'vdom':'root'}
    snapshot = item.snapshot
    snapshot['destinations'].append(destination)
    InstallationRequest.objects.filter(pk=item.pk).update(snapshot=snapshot,payload_digest=installation_digest(snapshot),execution_status='RUNNING',started_at=timezone.now())
    pending=InstallationTarget.objects.create(request=item,vdom=second,destination=destination)
    ExecutorLease.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
    acquire_lease('replacement')
    assert reconcile_installation(actor=scope[1],request_id=item.pk).execution_status == 'PENDING'
    first_steps = first.steps.count()
    assert execute_next(owner_id='replacement').execution_status == 'SUCCEEDED'
    first.refresh_from_db(); pending.refresh_from_db()
    assert first.steps.count() == first_steps
    assert pending.execution_status == 'SUCCEEDED'


def test_reconciliation_updates_recreated_group_provenance(installation, device, scope):
    from apps.changes.models import InstalledResource
    from apps.changes.installation_executor import execute_installation_target
    from apps.changes.installation_reconciliation import reconcile_installation
    from apps.accounts.models import GroupGrant
    GroupGrant.objects.create(user=scope[1],firewall_group=group_for(scope[2]),capability='administer')
    target = installation[0].targets.get()
    resource = InstalledResource.objects.create(vdom=scope[2],resource_type='group',name='portal_group',originating_target=target,revision=99)
    device['groups'] = {}
    device['mode'] = 'bad_group_read'
    assert execute_installation_target(target_id=target.pk,owner_id='worker').execution_status == 'RECONCILIATION_REQUIRED'
    device['mode'] = 'success'
    assert reconcile_installation(actor=scope[1],request_id=installation[0].pk).execution_status == 'SUCCEEDED'
    resource.refresh_from_db()
    assert resource.revision == 1
