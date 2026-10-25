# Backup and restore

Use `python manage.py backup_database PATH_TO_NEW_BACKUP.sqlite3` to create a consistent SQLite snapshot. Existing paths are refused. The command uses SQLite's backup API and verifies integrity; copying a live database file directly is not a substitute.

Back up deployment configuration and encryption keys separately to access-controlled encrypted storage. A database backup without the corresponding keys cannot recover stored credentials. Keep old key versions as long as backups encrypted under those keys exist.

Back up uploaded profile images in `data/` alongside the database and preserve their ownership.

For restoration, stop the combined application container with `docker compose stop web` (this stops both web and runner), preserve the current database as a recovery copy, restore the selected snapshot to `data/portal.sqlite3`, and restore the matching key ring. Keep the same Django secret if existing sessions must remain valid, or rotate it to invalidate sessions intentionally. Apply migrations, verify database integrity and credential decryption, and reconcile previously running or uncertain changes before restarting the executor. Confirm firewall state without replaying old requests.

The automated restore rehearsal writes a committed marker to an isolated SQLite file, runs the actual backup command, opens the snapshot as a restored database, checks integrity and content, and verifies overwrite refusal. It does not certify the target host's storage encryption or backup retention policy.
