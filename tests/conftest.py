from tests.group_helpers import group_for
import pytest
from cryptography.fernet import Fernet
from apps.accounts.models import User, GroupGrant
from apps.firewalls.models import Firewall, VDOM


@pytest.fixture
def scope(db, settings):
    settings.PORTAL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    fw = Firewall(name='Edge', hostname='192.0.2.1', allowed_namespace='portal_')
    fw.set_token('test-secret')
    fw.save()
    vdom = VDOM.objects.create(firewall=fw, name='root')
    operator = User.objects.create_user('operator', password='test-password')
    approver = User.objects.create_user('approver', password='test-password')
    for user, caps in [(operator, ['view','submit']), (approver, ['view','approve'])]:
        for cap in caps:
            GroupGrant.objects.create(user=user, firewall_group=group_for(vdom), capability=cap)
    return operator, approver, vdom
