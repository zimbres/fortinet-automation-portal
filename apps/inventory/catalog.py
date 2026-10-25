"""Local catalog mutations. No device reads or writes belong here."""
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from apps.accounts.permissions import require_catalog_capability, require_address_group_creation
from apps.audit.services import record_event
from apps.fortinet.schemas import validate_name
from .models import CatalogEntry, AddressObject, AddressGroup
from .restrictions import normalize_restriction, check_address_restrictions


def normalize_address(name, kind, value):
    name = validate_name(name.strip())
    value = value.strip()
    return name, normalize_restriction(kind, value)


def _entry(actor, name, entry_type, entry_id, revision):
    validate_name(name)
    if entry_id is None:
        return CatalogEntry.objects.create(name=name, entry_type=entry_type, created_by=actor, updated_by=actor)
    if revision is None or not CatalogEntry.objects.filter(pk=entry_id, entry_type=entry_type, revision=revision).update(
        name=name, revision=F('revision') + 1, updated_by=actor, updated_at=timezone.now()
    ):
        raise ValidationError('This catalog entry changed. Reload it before saving.')
    return CatalogEntry.objects.get(pk=entry_id)


def save_address(*, actor, name, kind, value, entry_id=None, expected_revision=None, group_id=None, override_restrictions=False):
    require_catalog_capability(actor, 'catalog_manage')
    name, value = normalize_address(name, kind, value)
    try:
        with transaction.atomic():
            matches = check_address_restrictions(actor=actor, kind=kind, value=value, override=override_restrictions)
            entry = _entry(actor, name, 'address', entry_id, expected_revision)
            obj, _ = AddressObject.objects.update_or_create(entry=entry, defaults={'kind': kind, 'value': value})
            if group_id is not None:
                add_objects_to_group(actor=actor, group_id=group_id, object_ids=[obj.pk])
            if override_restrictions:
                for rule in matches:
                    record_event(actor=actor, event_type='catalog.restriction_overridden',
                                 metadata={'entry_id': entry.pk, 'target_id': rule.pk, 'object_name': entry.name})
            record_event(actor=actor, event_type='catalog.updated' if entry_id else 'catalog.created', metadata={'object_name': name, 'entry_id': entry.pk})
            return obj
    except IntegrityError:
        raise ValidationError('An object or address group already uses this name.') from None


def save_address_group(*, actor, name, member_ids, entry_id=None, expected_revision=None, description=None):
    require_catalog_capability(actor, 'catalog_manage')
    if entry_id is None:
        require_address_group_creation(actor)
    name = validate_name(name.strip())
    if description is not None and (not isinstance(description,str) or len(description) > 500):
        raise ValidationError('The description must be at most 500 characters.')
    ids = set(member_ids)
    if AddressObject.objects.filter(pk__in=ids).count() != len(ids):
        raise ValidationError('One or more selected objects no longer exist.')
    try:
        with transaction.atomic():
            entry = _entry(actor, name, 'group', entry_id, expected_revision)
            group, _ = AddressGroup.objects.get_or_create(entry=entry)
            if description is not None:
                group.description = description.strip()
                group.save(update_fields=['description'])
            group.members.set(ids)
            record_event(actor=actor, event_type='catalog.updated' if entry_id else 'catalog.created', metadata={'object_name': name, 'entry_id': entry.pk})
            return group
    except IntegrityError:
        raise ValidationError('An object or address group already uses this name.') from None


@transaction.atomic
def delete_catalog_entry(*, actor, entry_id, expected_revision):
    require_catalog_capability(actor, 'catalog_manage')
    entry = CatalogEntry.objects.get(pk=entry_id)
    if entry.revision != expected_revision:
        raise ValidationError('This catalog entry changed. Reload it before deleting.')
    if entry.entry_type == 'address' and entry.address.address_groups.exists():
        raise ValidationError('Remove this object from local address groups before deleting it.')
    # Acquire a write claim before deleting; concurrent stale mutations cannot win.
    if not CatalogEntry.objects.filter(pk=entry_id, revision=expected_revision).update(revision=F('revision') + 1):
        raise ValidationError('This catalog entry changed.')
    record_event(actor=actor, event_type='catalog.deleted', metadata={'object_name': entry.name, 'entry_id': entry.pk})
    entry.delete()


@transaction.atomic
def add_objects_to_group(*, actor, group_id, object_ids, expected_revision=None):
    require_catalog_capability(actor, 'catalog_manage')
    group = AddressGroup.objects.select_related('entry').filter(pk=group_id).first()
    if group is None:
        raise ValidationError('The selected address group no longer exists. Select a group again.')
    revision = group.entry.revision if expected_revision is None else expected_revision
    ids = set(object_ids)
    if AddressObject.objects.filter(pk__in=ids).count() != len(ids):
        raise ValidationError('One or more objects no longer exist.')
    if not CatalogEntry.objects.filter(pk=group.entry_id, revision=revision).update(
        revision=F('revision') + 1, updated_by=actor, updated_at=timezone.now()
    ):
        raise ValidationError('The selected address group changed. Preview or reload before saving.')
    group.members.add(*ids)
    record_event(actor=actor, event_type='catalog.updated', metadata={'entry_id':group.entry_id,'object_name':group.entry.name,'count':len(ids)})
    return group


def validate_address_selection(*, actor, selections):
    require_catalog_capability(actor, 'catalog_manage')
    if not selections or len(selections) > 500:
        raise ValidationError('Select between 1 and 500 objects.')
    if any(not isinstance(key,int) or key < 1 or not isinstance(value,int) or value < 1 for key,value in selections.items()):
        raise ValidationError('Invalid object selection. Reload the list.')
    entries = list(CatalogEntry.objects.filter(pk__in=selections,entry_type='address').select_related('address').order_by('name'))
    if len(entries) != len(selections):
        raise ValidationError('One or more selected objects no longer exist. Reload the list.')
    for entry in entries:
        if entry.revision != selections[entry.pk]:
            raise ValidationError(f'{entry.name} changed. Reload the list before deleting.')
        if entry.address.address_groups.exists():
            raise ValidationError(f'{entry.name} belongs to an address group. Remove its group memberships before deleting.')
    return entries


@transaction.atomic
def bulk_delete_addresses(*, actor, selections):
    entries = validate_address_selection(actor=actor,selections=selections)
    for entry in entries:
        delete_catalog_entry(actor=actor,entry_id=entry.pk,expected_revision=selections[entry.pk])
    return len(entries)
