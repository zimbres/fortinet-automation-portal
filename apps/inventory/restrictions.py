"""Restricted address configuration and shared server-side matching."""
from ipaddress import ip_network
import re
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from apps.accounts.permissions import require_restriction_management
from apps.audit.services import record_event
from apps.fortinet.schemas import address_payload
from .models import AddressRestriction


def normalize_restriction(kind, value):
    value = value.strip()
    if kind == 'subnet':
        try:
            value = str(ip_network(value, strict=False))
        except ValueError:
            raise ValidationError('Enter a valid IPv4 host or subnet.') from None
    payload = address_payload('restriction', kind, value)
    if kind != 'subnet' and len(payload['fqdn']) > 253:
        raise ValidationError('Address values must be at most 253 characters, including the wildcard prefix.')
    if kind != 'subnet' and re.fullmatch(r'[0-9.]+', payload['fqdn'].removeprefix('*.')):
        raise ValidationError('Enter a domain name; use IPv4 host / subnet for IP addresses.')
    return value if kind == 'subnet' else payload['fqdn']


def matching_restrictions(kind, value):
    value = normalize_restriction(kind, value)
    rules = AddressRestriction.objects.all()
    if kind == 'subnet':
        network = ip_network(value)
        return [rule for rule in rules.filter(kind='subnet') if network.overlaps(ip_network(rule.value))]
    base = value.removeprefix('*.')
    matches = []
    for rule in rules.exclude(kind='subnet'):
        root = rule.value.removeprefix('*.')
        descendant = base.endswith('.' + root)
        if kind == 'wildcard_fqdn':
            matched = base == root or descendant or root.endswith('.' + base)
        else:
            matched = descendant or (base == root and rule.kind == 'fqdn')
        if matched:
            matches.append(rule)
    return matches


class RestrictedAddressError(ValidationError):
    """A refusal that bulk callers may skip without swallowing other errors."""


def check_address_restrictions(*, actor, kind, value, override=False):
    if override:
        require_restriction_management(actor)
    matches = matching_restrictions(kind, value)
    if matches and not override:
        raise RestrictedAddressError(
            f'{value} is restricted by: ' + ', '.join(rule.value for rule in matches)
        )
    return matches


@transaction.atomic
def save_restriction(*, actor, kind, value, restriction_id=None):
    require_restriction_management(actor)
    value = normalize_restriction(kind, value)
    try:
        with transaction.atomic():
            if restriction_id is None:
                rule, created = AddressRestriction.objects.get_or_create(
                    kind=kind, value=value, defaults={'created_by': actor, 'updated_by': actor}
                )
                if not created:
                    return rule
            else:
                rule = AddressRestriction.objects.select_for_update().get(pk=restriction_id)
                rule.kind, rule.value, rule.updated_by = kind, value, actor
                rule.save(update_fields=['kind', 'value', 'updated_by', 'updated_at'])
    except IntegrityError:
        raise ValidationError('This restricted address already exists.') from None
    record_event(actor=actor, event_type='restriction.updated' if restriction_id else 'restriction.created',
                 metadata={'target_id': rule.pk, 'object_name': rule.value, 'operation': rule.kind})
    return rule


@transaction.atomic
def delete_restriction(*, actor, restriction_id):
    require_restriction_management(actor)
    rule = AddressRestriction.objects.select_for_update().get(pk=restriction_id)
    record_event(actor=actor, event_type='restriction.deleted',
                 metadata={'target_id': rule.pk, 'object_name': rule.value, 'operation': rule.kind})
    rule.delete()
