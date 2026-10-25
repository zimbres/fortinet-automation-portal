from io import StringIO
from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError


def test_worker_retries_temporary_sqlite_lock():
    output=StringIO()
    with patch('apps.changes.management.commands.run_executor.execute_next',side_effect=[OperationalError('database is locked'),None]) as execute, patch('apps.changes.management.commands.run_executor.recover_locked_execution') as recover, patch('apps.changes.management.commands.run_executor.time.sleep',side_effect=[None,KeyboardInterrupt]):
        with pytest.raises(KeyboardInterrupt): call_command('run_executor',stderr=output,stdout=StringIO())
    assert execute.call_count == 2
    recover.assert_called_once()
    assert 'locked' in output.getvalue().lower()


def test_once_reports_temporary_database_lock():
    with patch('apps.changes.management.commands.run_executor.execute_next',side_effect=OperationalError('database is locked')):
        with pytest.raises(CommandError,match='temporarily locked'): call_command('run_executor',once=True,stderr=StringIO())


def test_worker_does_not_hide_other_database_errors():
    with patch('apps.changes.management.commands.run_executor.execute_next',side_effect=OperationalError('no such table')):
        with pytest.raises(OperationalError,match='no such table'): call_command('run_executor',once=True,stderr=StringIO())


@pytest.mark.django_db
def test_locked_running_installation_requires_reconciliation(scope):
    from apps.changes.executor import acquire_lease,recover_locked_execution
    from apps.changes.models import InstallationRequest,InstallationTarget
    acquire_lease('worker')
    item=InstallationRequest.objects.create(requester=scope[0],snapshot={},payload_digest='a'*64,idempotency_key='lock',execution_status='RUNNING')
    target=InstallationTarget.objects.create(request=item,vdom=scope[2],destination={},execution_status='RUNNING')
    recover_locked_execution(owner_id='worker')
    item.refresh_from_db(); target.refresh_from_db()
    assert item.recovery_required and item.execution_status == 'RECONCILIATION_REQUIRED'
    assert target.execution_status == 'RECONCILIATION_REQUIRED'


@pytest.mark.django_db
def test_lock_recovery_cannot_change_another_workers_jobs(scope):
    from apps.changes.executor import acquire_lease,recover_locked_execution
    from apps.changes.models import InstallationRequest
    acquire_lease('other')
    item=InstallationRequest.objects.create(requester=scope[0],snapshot={},payload_digest='a'*64,idempotency_key='lock',execution_status='RUNNING')
    recover_locked_execution(owner_id='worker')
    item.refresh_from_db()
    assert item.execution_status == 'RUNNING'
