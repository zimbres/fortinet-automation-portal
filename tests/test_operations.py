import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
import pytest


def test_sqlite_backup_restores_committed_data(tmp_path, settings, monkeypatch):
    original,backup = tmp_path/'original.sqlite3',tmp_path/'backup.sqlite3'
    with sqlite3.connect(original) as db:
        db.execute('CREATE TABLE check_data (value TEXT)')
        db.execute("INSERT INTO check_data VALUES ('preserved')")
    monkeypatch.setitem(settings.DATABASES['default'],'NAME',str(original))
    call_command('backup_database',str(backup))
    with pytest.raises(CommandError): call_command('backup_database',str(backup))
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT value FROM check_data').fetchone()[0] == 'preserved'


def test_production_rejects_missing_secrets(tmp_path):
    env = os.environ.copy()
    env.update(DJANGO_SETTINGS_MODULE='config.settings.production')
    env.pop('DJANGO_SECRET_KEY',None)
    env.pop('DJANGO_SECRET_KEY_FILE',None)
    result = subprocess.run([sys.executable,'manage.py','check'],env=env,capture_output=True,text=True)
    assert result.returncode != 0
    assert 'DJANGO_SECRET_KEY' in result.stderr
