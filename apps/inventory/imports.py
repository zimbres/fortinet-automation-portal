"""Bounded create-only raw-list and CSV imports, stored server-side between preview and confirm."""
import csv
import hashlib
import io
import json
import re
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.accounts.permissions import require_catalog_capability, require_restriction_management
from apps.audit.services import record_event
from .catalog import normalize_address, save_address, add_objects_to_group
from .models import CatalogImport, CatalogEntry, AddressGroup
from .restrictions import check_address_restrictions, RestrictedAddressError


def _digest(rows, group_snapshot=None, override_restrictions=False):
    payload = rows if group_snapshot is None else {'rows':rows,'group':group_snapshot}
    if override_restrictions:
        payload = {'input':payload, 'override_restrictions':True}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _raw_address(value, prefix):
    original=value.strip()
    value=original.lower()
    if value.startswith('*.'):
        kind='wildcard_fqdn'
    elif '/' in value or ':' in value or re.fullmatch(r'[0-9.]+',value):
        kind='subnet'
    else:
        kind='fqdn'
    # Names preserve the supplied address; values still use catalog validation
    # and normalization. Reject overlength names rather than renaming them.
    name,value=normalize_address(prefix+original,kind,original)
    return name,kind,value


def preview_import(*, actor, content, prefix='', group_id=None, override_restrictions=False):
    require_catalog_capability(actor, 'catalog_manage')
    if override_restrictions:
        require_restriction_management(actor)
    if len(content) > 1048576:
        raise ValidationError('Imports must be at most 1 MiB.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{0,40}',prefix):
        raise ValidationError('Use an object prefix of up to 40 letters, digits, dots, underscores or hyphens.')
    group_snapshot = None
    if group_id is not None:
        group = AddressGroup.objects.select_related('entry').filter(pk=group_id).first()
        if group is None:
            raise ValidationError('The selected address group no longer exists.')
        group_snapshot = {'id':group.pk,'name':group.entry.name,'revision':group.entry.revision}
    rows, errors, names, refused = [], [], set(), []
    try:
        text=content.decode('utf-8-sig')
        first_line=next((line for line in text.splitlines() if line.strip()),'')
        header=next(csv.reader([first_line],strict=True),[])
        is_csv=header==['name','kind','value']
        if is_csv:
            reader=csv.DictReader(io.StringIO(text.lstrip(),newline=''),strict=True)
            source=enumerate(reader,2)
        else:
            source=((number,line) for number,line in enumerate(text.splitlines(),1) if line.strip())
        count=0
        for number,row in source:
            count+=1
            if count>1000:
                errors.append('The import exceeds 1,000 rows.')
                break
            try:
                if is_csv:
                    if None in row or any(v is None for v in row.values()):
                        raise ValidationError('Each row must have exactly three cells.')
                    kind=row['kind']
                    name,value=normalize_address(prefix+row['name'].strip(),kind,row['value'])
                else:
                    name,kind,value=_raw_address(row,prefix)
                if name in names or CatalogEntry.objects.filter(name=name).exists():
                    raise ValidationError('Duplicate or existing catalog name.')
                names.add(name)
                rows.append({'name':name,'kind':kind,'value':value})
                try:
                    check_address_restrictions(actor=actor, kind=kind, value=value, override=override_restrictions)
                except RestrictedAddressError as exc:
                    refused.append({'name':name, 'value':value, 'reason':' '.join(exc.messages)})
            except ValidationError as exc:
                errors.append(f'{"Row" if is_csv else "Line"} {number}: {" ".join(exc.messages)}')
    except (UnicodeDecodeError,csv.Error) as exc:
        errors.append('Invalid UTF-8 or CSV data.')
    if not rows and not errors:
        errors.append('Include at least one address row.')
    return CatalogImport.objects.create(actor=actor, rows=rows, errors=errors, refused_rows=refused,
        override_restrictions=override_restrictions, digest=_digest(rows, group_snapshot, override_restrictions),
        group_snapshot=group_snapshot, expires_at=timezone.now()+timedelta(minutes=30))


@transaction.atomic
def confirm_import(*, actor, token):
    require_catalog_capability(actor, 'catalog_manage')
    batch = CatalogImport.objects.get(pk=token)
    if batch.actor_id != actor.pk:
        raise PermissionDenied('This preview belongs to another user.')
    if batch.override_restrictions:
        require_restriction_management(actor)
    if batch.completed_at:
        return list(batch.created_objects.order_by('pk'))
    if batch.expires_at <= timezone.now() or batch.errors or batch.digest != _digest(batch.rows, batch.group_snapshot, batch.override_restrictions):
        raise ValidationError('Preview is invalid or expired. Preview the list again.')
    # Fatal validation must hold even when restrictions refuse every row.
    if CatalogEntry.objects.filter(name__in=[row['name'] for row in batch.rows]).exists():
        raise ValidationError('Duplicate or existing catalog name. Preview the list again.')
    if batch.group_snapshot is not None:
        group = AddressGroup.objects.select_for_update().select_related('entry').filter(pk=batch.group_snapshot['id']).first()
        if group is None:
            raise ValidationError('The selected address group no longer exists. Preview the list again.')
        if group.entry.revision != batch.group_snapshot['revision']:
            raise ValidationError('The selected address group changed. Preview the list again.')
    if not CatalogImport.objects.filter(pk=token, completed_at__isnull=True).update(completed_at=timezone.now()):
        raise ValidationError('This import is already being confirmed.')
    created, refused = [], []
    for row in batch.rows:
        try:
            created.append(save_address(actor=actor, **row, override_restrictions=batch.override_restrictions))
        except RestrictedAddressError as exc:
            refused.append({'name':row['name'], 'value':row['value'], 'reason':' '.join(exc.messages)})
    if batch.group_snapshot is not None and created:
        add_objects_to_group(actor=actor, group_id=batch.group_snapshot['id'], object_ids=[obj.pk for obj in created], expected_revision=batch.group_snapshot['revision'])
    batch.created_objects.set(created)
    batch.refused_rows = refused
    batch.save(update_fields=['refused_rows'])
    record_event(actor=actor, event_type='catalog.imported', metadata={'batch_id': str(batch.pk), 'count': len(created), 'object_ids': ','.join(str(obj.pk) for obj in created)})
    return created
