from dataclasses import dataclass
from urllib.parse import quote
import httpx
from .exceptions import FortinetError, UncertainResult


@dataclass(frozen=True)
class ReferenceReport:
    complete: bool
    references: tuple = ()


class FortinetClient:
    def __init__(self, firewall, vdom, *, transport=None):
        self.vdom = vdom.name
        hostname = firewall.hostname
        if ':' in hostname and not hostname.startswith('['):
            hostname = f'[{hostname}]'
        protocol = getattr(firewall, 'protocol', 'https')
        if protocol not in ('http','https'):
            raise ValueError('Select HTTP or HTTPS for the firewall connection.')
        self.http = httpx.Client(base_url=f'{protocol}://{hostname}:{firewall.port}',
            headers={'Authorization': f'Bearer {firewall.get_token()}'}, verify=False,
            follow_redirects=False, timeout=httpx.Timeout(15, connect=5),
            transport=transport, trust_env=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def request(self, method, path, payload=None, extra=None):
        mutating = method != 'GET'
        try:
            response = self.http.request(method, path, params={'vdom': self.vdom, **(extra or {})}, json=payload)
        except httpx.TransportError:
            error = UncertainResult if mutating else FortinetError
            raise error('The firewall response could not be confirmed.') from None
        if response.status_code == 404 and method == 'GET':
            return None
        if response.status_code >= 500 and mutating:
            raise UncertainResult('The firewall returned an uncertain server error.')
        if not 200 <= response.status_code < 300:
            raise FortinetError(f'The firewall rejected the request (HTTP {response.status_code}).')
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError
        except ValueError:
            error = UncertainResult if mutating else FortinetError
            raise error('The firewall returned an invalid response.') from None
        if result.get('status') != 'success':
            # A successful HTTP response with an ambiguous body is never proof
            # that a mutation did not occur.
            error = UncertainResult if mutating else FortinetError
            raise error('The firewall did not confirm success.')
        return result

    def listing(self, resource):
        records, start = [], 0
        for _ in range(1000):
            result = self.request('GET', f'/api/v2/cmdb/firewall/{resource}', extra={'start': start, 'count': 500})
            if result is None or not isinstance(result.get('results'), list):
                raise FortinetError('Incomplete inventory response.')
            records.extend(result['results'])
            if not result.get('limit_reached', False):
                return records
            next_index = result.get('next_idx')
            if not isinstance(next_index, int) or next_index <= start:
                raise FortinetError('Inventory pagination could not be completed.')
            start = next_index
        raise FortinetError('Inventory exceeded the supported pagination limit.')

    def get(self, resource, name):
        data = self.request('GET', f'/api/v2/cmdb/firewall/{resource}/{quote(name, safe="")}')
        if data is None:
            return None
        results = data.get('results')
        if isinstance(results, list):
            return results[0] if len(results) == 1 else None
        if isinstance(results, dict):
            return results
        raise FortinetError('Invalid object response.')

    def list_addresses(self): return self.listing('address')
    def list_groups(self): return self.listing('addrgrp')
    def list_policies(self): return self.listing('policy')
    def get_address(self, name): return self.get('address', name)
    def get_group(self, name): return self.get('addrgrp', name)
    def create_address(self, payload):
        return self.request('POST', '/api/v2/cmdb/firewall/address', payload)
    def create_group(self, payload):
        return self.request('POST', '/api/v2/cmdb/firewall/addrgrp', payload)
    def update_address(self, name, payload):
        return self.request('PUT', f'/api/v2/cmdb/firewall/address/{quote(name, safe="")}', payload)
    def delete_address(self, name):
        return self.request('DELETE', f'/api/v2/cmdb/firewall/address/{quote(name, safe="")}')
    def set_group_members(self, name, members):
        return self.request('PUT', f'/api/v2/cmdb/firewall/addrgrp/{quote(name, safe="")}', {'member': [{'name': x} for x in members]})
    def get_reference_report(self, name):
        # Policy/group scans alone cannot establish all CMDB references.
        # Keep destructive operations blocked until the version-specific
        # authoritative reference endpoint has been validated.
        return ReferenceReport(complete=False)
