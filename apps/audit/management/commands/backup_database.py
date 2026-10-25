import os
import sqlite3
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create a consistent SQLite backup without overwriting existing files.'

    def add_arguments(self,parser):
        parser.add_argument('destination')

    def handle(self,*args,**options):
        source = Path(settings.DATABASES['default']['NAME']).resolve()
        destination = Path(options['destination']).resolve()
        if not source.is_file():
            raise CommandError('The source database does not exist.')
        try:
            fd = os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        except (FileExistsError,OSError):
            raise CommandError('Choose a new backup path in an existing writable directory.') from None
        try:
            with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
                with sqlite3.connect(destination) as backup:
                    original.backup(backup)
                    if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise CommandError('Backup integrity verification failed.')
        except sqlite3.Error:
            raise CommandError('Backup could not be completed. Do not use the destination file.') from None
        self.stdout.write(f'Consistent backup created: {destination}')
