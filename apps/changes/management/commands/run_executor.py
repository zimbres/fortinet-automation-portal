import time
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError
from apps.changes.executor import execute_next, recover_locked_execution
from apps.fortinet.exceptions import FortinetError


class Command(BaseCommand):
    help = 'Run the single approved-change executor.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        owner = str(uuid.uuid4())
        recovery_needed = False
        while True:
            try:
                if recovery_needed:
                    recover_locked_execution(owner_id=owner)
                    recovery_needed = False
                item = execute_next(owner_id=owner)
            except OperationalError as exc:
                if not any(message in str(exc).lower() for message in ('database is locked','database table is locked')):
                    raise
                if options['once']:
                    raise CommandError('The database is temporarily locked. Retry after the current transaction finishes.') from None
                self.stderr.write('Database temporarily locked; retrying in 3 seconds. Interrupted work will require reconciliation.')
                recovery_needed = True
                time.sleep(3)
                continue
            except FortinetError as exc:
                raise CommandError(str(exc)) from None
            if item:
                self.stdout.write(f'{item.pk}: {item.execution_status}')
            if options['once']:
                return
            time.sleep(3)
