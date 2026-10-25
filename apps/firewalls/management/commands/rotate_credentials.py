from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ImproperlyConfigured
from apps.firewalls.models import Firewall
from apps.audit.services import record_event


class Command(BaseCommand):
    help = 'Re-encrypt stored credentials with the first key in the externally supplied key ring.'

    @transaction.atomic
    def handle(self,*args,**options):
        count = 0
        try:
            for firewall in Firewall.objects.exclude(encrypted_token=''):
                previous = firewall.encrypted_token
                firewall.set_token(firewall.get_token())
                if not Firewall.objects.filter(pk=firewall.pk,encrypted_token=previous).update(encrypted_token=firewall.encrypted_token):
                    raise CommandError('Credential changed concurrently. Rotation rolled back.')
                count += 1
        except (ValueError,ImproperlyConfigured):
            raise CommandError('Rotation failed. Check the complete key ring; changes were rolled back.') from None
        record_event(actor=None,event_type='credentials.rotated',metadata={'status':'completed'})
        self.stdout.write(f'Rotated {count} credential(s). Keep old keys until backups have been addressed.')
