"""Bounded, independently validated imports of restricted address values."""
import csv
import io
import re
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.accounts.permissions import require_restriction_management
from .models import AddressRestriction
from .restrictions import normalize_restriction, save_restriction


@transaction.atomic
def import_restrictions(*, actor, content):
    require_restriction_management(actor)
    if len(content) > 1048576:
        raise ValidationError('Imports must be at most 1 MiB.')
    normalized, errors = [], []
    try:
        text = content.decode('utf-8-sig')
        first = next((line for line in text.splitlines() if line.strip()), '')
        is_csv = next(csv.reader([first], strict=True), []) == ['name', 'kind', 'value']
        source = enumerate(csv.DictReader(io.StringIO(text.lstrip(), newline=''), strict=True), 2) if is_csv else (
            (number, line) for number, line in enumerate(text.splitlines(), 1) if line.strip()
        )
        count = 0
        for number, row in source:
            count += 1
            if count > 1000:
                raise ValidationError('Imports must contain at most 1,000 rows. Nothing was imported.')
            try:
                if is_csv:
                    if None in row or any(value is None for value in row.values()):
                        raise ValidationError('Each CSV row must have exactly three cells.')
                    kind, value = row['kind'], row['value']
                else:
                    value = row.strip()
                    kind = 'wildcard_fqdn' if value.startswith('*.') else (
                        'subnet' if '/' in value or ':' in value or re.fullmatch(r'[0-9.]+', value) else 'fqdn'
                    )
                normalized.append((kind, normalize_restriction(kind, value)))
            except ValidationError as exc:
                errors.append(f'{"Row" if is_csv else "Line"} {number}: {" ".join(exc.messages)}')
    except (UnicodeDecodeError, csv.Error):
        raise ValidationError('Invalid UTF-8 or CSV data. Nothing was imported.') from None
    if not normalized and not errors:
        raise ValidationError('Include at least one address.')
    created, duplicates = 0, 0
    for kind, value in normalized:
        if AddressRestriction.objects.filter(kind=kind, value=value).exists():
            duplicates += 1
        else:
            save_restriction(actor=actor, kind=kind, value=value)
            created += 1
    return {'created':created, 'duplicates':duplicates, 'errors':errors}
