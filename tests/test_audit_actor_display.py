import json
import logging
import pytest
from apps.audit.models import AuditEvent
from apps.audit.logging import JsonFormatter


@pytest.mark.parametrize('kind,label', [('change.execution_finished','Executor (background runner)'),('installation.target_finished','Executor (background runner)'),('login.failed','Unauthenticated login attempt'),('credentials.rotated','Credential rotation command'),('other.event','System')])
def test_actor_labels_for_automated_events(kind,label):
    assert AuditEvent(event_type=kind).actor_display == label


def test_stdout_includes_actor_description():
    record=logging.LogRecord('portal.audit',logging.INFO,'',0,'audit_event',(),None)
    record.actor_label='Executor (background runner)'
    assert json.loads(JsonFormatter().format(record))['actor']=='Executor (background runner)'


@pytest.mark.django_db
def test_audit_page_labels_old_runner_events_and_keeps_user_actor(client):
    from apps.accounts.models import User
    from apps.audit.services import record_event
    admin=User.objects.create_user(username='admin@example.com',is_superuser=True)
    historical=AuditEvent.objects.create(actor=None,event_type='installation.target_finished')
    user_event=record_event(actor=admin,event_type='change.approved')
    assert user_event.actor_display == admin.username
    client.force_login(admin)
    response=client.get('/audit/')
    assert response.status_code == 200
    assert b'Executor (background runner)' in response.content
    assert b'System / unauthenticated' not in response.content
    historical.refresh_from_db()
    assert historical.actor_id is None
