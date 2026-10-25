import pytest
import httpx


@pytest.mark.parametrize('kind,value,expected', [
    ('subnet', '192.0.2.3', {'type': 'ipmask', 'subnet': '192.0.2.3 255.255.255.255'}),
    ('subnet', '192.0.2.0/24', {'type': 'ipmask', 'subnet': '192.0.2.0 255.255.255.0'}),
    ('fqdn', 'Example.COM', {'type': 'fqdn', 'fqdn': 'example.com'}),
    ('wildcard_fqdn', '*.example.com', {'type': 'fqdn', 'fqdn': '*.example.com'}),
])
def test_address_payload(kind, value, expected):
    from apps.fortinet.schemas import address_payload
    assert address_payload('portal_test', kind, value) == {'name': 'portal_test', **expected}


@pytest.mark.parametrize('kind,value', [('subnet','::1'), ('subnet','192.0.2.3/24'),
    ('fqdn','https://example.com'), ('fqdn','*.example.com'), ('wildcard_fqdn','*evil.com')])
def test_reject_invalid_address(kind, value):
    from apps.fortinet.schemas import address_payload
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        address_payload('portal_test', kind, value)


def test_unknown_version_cannot_write():
    from apps.fortinet.capabilities import require_write_capability
    from apps.fortinet.exceptions import FortinetError
    with pytest.raises(FortinetError):
        require_write_capability('7.4.unknown', 'create_address')


def test_live_validated_version_supports_only_proven_operations():
    from apps.fortinet.capabilities import require_write_capability
    from apps.fortinet.exceptions import FortinetError
    scope=('http','192.168.100.38',80,'root')
    for operation in ['install_address_subnet','install_address_fqdn','install_address_wildcard_fqdn','create_group','install_group_members']:
        require_write_capability('v7.0.13',operation,scope)
    for operation in ['delete_address']:
        with pytest.raises(FortinetError): require_write_capability('v7.0.13',operation,scope)
    with pytest.raises(FortinetError): require_write_capability('v7.0.14','install_address_subnet',scope)
    with pytest.raises(FortinetError): require_write_capability('v7.0.13','install_address_subnet')
    for other_scope in [('http','192.168.100.39',80,'root'),('https','192.168.100.38',443,'root'),('http','192.168.100.38',80,'other')]:
        for operation in ('install_address_subnet','install_address_fqdn','install_address_wildcard_fqdn'):
            with pytest.raises(FortinetError): require_write_capability('v7.0.13',operation,other_scope)
    with pytest.raises(FortinetError,match='install_address_fqdn.*v7.0.14'):
        require_write_capability('v7.0.14','install_address_fqdn',scope)



def test_client_scopes_and_escapes_names():
    from apps.fortinet.client import FortinetClient
    from types import SimpleNamespace
    fw = SimpleNamespace(hostname='192.0.2.1', port=443, get_token=lambda: 'not-logged')
    seen = []
    def remote(request):
        seen.append(request)
        return httpx.Response(200, json={'status':'success', 'results':[{'name':'a/b'}]})
    with FortinetClient(fw, SimpleNamespace(name='root'), transport=httpx.MockTransport(remote)) as client:
        assert client.get_address('a/b')['name'] == 'a/b'
    assert seen[0].url.params['vdom'] == 'root'
    assert 'a%2Fb' in str(seen[0].url)


def test_write_transport_error_is_uncertain_and_sanitized():
    from apps.fortinet.client import FortinetClient
    from apps.fortinet.exceptions import UncertainResult
    from types import SimpleNamespace
    def remote(request):
        raise httpx.ReadTimeout('sensitive token', request=request)
    fw = SimpleNamespace(hostname='192.0.2.1', port=443, get_token=lambda: 'secret')
    with FortinetClient(fw, SimpleNamespace(name='root'), transport=httpx.MockTransport(remote)) as client:
        with pytest.raises(UncertainResult) as error:
            client.create_address({'name':'portal_x'})
    assert 'sensitive' not in str(error.value)
