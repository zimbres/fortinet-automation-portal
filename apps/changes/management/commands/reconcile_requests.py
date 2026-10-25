from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import User
from apps.changes.reconciliation import reconcile_change
from apps.fortinet.exceptions import FortinetError
from django.core.exceptions import PermissionDenied, ValidationError


class Command(BaseCommand):
    help = 'Read-only reconciliation of one uncertain request as an authorized administrator.'

    def add_arguments(self,parser):
        parser.add_argument('request_id')
        parser.add_argument('--actor',required=True)
        parser.add_argument('--installation', action='store_true', help='Reconcile an installation request instead of a legacy request.')

    def handle(self,*args,**options):
        try:
            actor = User.objects.get(username=options['actor'],is_active=True)
            if options['installation']:
                from apps.changes.installation_reconciliation import reconcile_installation
                item = reconcile_installation(actor=actor, request_id=options['request_id'])
            else:
                item = reconcile_change(actor=actor,request_id=options['request_id'])
        except (User.DoesNotExist,FortinetError,PermissionDenied,ValidationError):
            raise CommandError('Reconciliation could not be completed for this actor and request.') from None
        self.stdout.write(f'{item.pk}: {item.execution_status}')
