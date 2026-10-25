import re
from ipaddress import ip_network
from django.core.exceptions import ValidationError


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.:@ */-]{1,79}', name):
        raise ValidationError('Use a name of up to 79 letters, digits, spaces, or . _ : @ - * / characters.')
    return name


def address_payload(name: str, kind: str, value: str) -> dict:
    validate_name(name)
    if kind == 'subnet':
        try:
            network = ip_network(value, strict=True)
            if network.version != 4:
                raise ValueError
        except ValueError:
            raise ValidationError('Enter an IPv4 host or a subnet with its network address.') from None
        return {'name': name, 'type': 'ipmask', 'subnet': f'{network.network_address} {network.netmask}'}
    if kind not in ('fqdn', 'wildcard_fqdn'):
        raise ValidationError('Unsupported address type.')
    value = value.strip().lower().rstrip('.')
    domain = value
    if kind == 'wildcard_fqdn':
        if not value.startswith('*.'):
            raise ValidationError('A wildcard FQDN must start with *.')
        domain = value[2:]
    if len(domain) > 253 or '.' not in domain or not all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')
    ):
        raise ValidationError('Enter a valid domain name without a scheme, port, or path.')
    return {'name': name, 'type': 'fqdn', 'fqdn': value}
