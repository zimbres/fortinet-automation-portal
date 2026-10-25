import pytest
from django.db import IntegrityError, transaction


@pytest.mark.django_db
def test_external_identity_pair_is_unique():
    from apps.accounts.models import User
    User.objects.create_user('alice', external_issuer='https://idp.example', external_subject='same')
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user('bob', external_issuer='https://idp.example', external_subject='same')


@pytest.mark.django_db
def test_audit_rejects_mutation_and_redacts_secrets():
    from apps.audit.services import record_event
    event = record_event(actor=None, event_type='test', metadata={'token': 'secret', 'safe': 'visible'})
    assert event.metadata == {'token': '[REDACTED]', 'safe': 'visible'}
    with pytest.raises(ValueError):
        event.delete()
    event.event_type = 'changed'
    with pytest.raises(ValueError):
        event.save()
