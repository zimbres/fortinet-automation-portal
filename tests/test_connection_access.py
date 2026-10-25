from unittest.mock import patch
from django.utils import timezone
import pytest
from apps.accounts.models import GroupGrant
from apps.firewalls.models import VDOM
pytestmark=pytest.mark.django_db


def test_superadmin_connection_check_does_not_require_group_grant(client,scope):
    user=scope[0]; user.is_superuser=True; user.save()
    GroupGrant.objects.filter(user=user).delete()
    client.force_login(user)
    with patch('apps.portal.views.FortinetClient') as remote:
        remote.return_value.__enter__.return_value.request.return_value={'status':'success','version':'test-version'}
        response=client.post(f'/vdom/{scope[2].pk}/check/')
    assert response.status_code==302 and response.url=='/firewalls/'
    remote.assert_called_once()
    scope[2].firewall.refresh_from_db()
    assert scope[2].firewall.observed_version=='test-version'


def test_connection_check_preserves_scope_permissions(client,scope):
    client.force_login(scope[0])
    with patch('apps.portal.views.FortinetClient') as remote:
        assert client.post(f'/vdom/{scope[2].pk}/check/').status_code==404
        remote.assert_not_called()


def test_superadmin_inactive_scopes_redirect_without_remote_call(client,scope):
    user=scope[0]; user.is_superuser=True; user.save(); client.force_login(user)
    for update in ({'enabled':False},{'enabled':False,'removed_at':timezone.now()}):
        VDOM.objects.filter(pk=scope[2].pk).update(**update)
        with patch('apps.portal.views.FortinetClient') as remote:
            response=client.post(f'/vdom/{scope[2].pk}/check/')
            assert response.status_code==302 and response.url=='/firewalls/'
            remote.assert_not_called()
