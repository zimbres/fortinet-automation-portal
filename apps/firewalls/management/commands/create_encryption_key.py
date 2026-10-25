import os
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create a new external encryption key file without overwriting existing keys.'

    def add_arguments(self, parser):
        parser.add_argument('--path',default=str(settings.BASE_DIR / '.cache' / 'encryption.keys'))

    def handle(self,*args,**options):
        path = Path(options['path'])
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            raise CommandError('The key file already exists. It was not modified.') from None
        with os.fdopen(fd,'wb') as stream:
            stream.write(Fernet.generate_key()+b'\n')
        self.stdout.write(f'Encryption key file created: {path}. Back it up separately and restrict its ACL.')
