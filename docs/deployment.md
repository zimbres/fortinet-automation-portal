# Deployment

The Compose stack is provided for validation on a Docker-enabled host. It runs Gunicorn and exactly one executor together in the `web` container, plus a separate unprivileged HTTPS Nginx proxy. Only proxy ports are published. Do not expose the Gunicorn port directly: production trusts the proxy's overwritten X-Forwarded-Proto header.

1. Create a protected `secrets/` directory outside source control. Supply files named `django_secret_key` (at least 50 random characters), `encryption_keys` (one Fernet key per line), `tls_certificate`, and `tls_private_key`. Supply `oidc_client_secret` as well; in explicit local mode it can be an empty placeholder because it is not read by Django.
2. Set `DJANGO_ALLOWED_HOSTS` to explicit hostnames and `PORTAL_AUTH_MODE` to `local` or `oidc`. Compose reads `.env`; direct Django commands do not. For OIDC configure issuer, client ID, authorization/token/UserInfo/JWKS endpoints. The secret is mounted separately. Use HTTPS IdP endpoints and matching redirect URI `https://HOST/oidc/callback/`.
3. Prepare `data/` with write permissions for application UID/GID 10001:10001 (for example, `sudo chown -R 10001:10001 data` on a Linux host). Use a local disk, not a network filesystem. Restrict host access to data and secret directories. Configure encrypted backups independently of the runtime container.
4. Run `docker compose config`, then `docker compose up --build -d`. The container migrates the database and collects static assets before starting Gunicorn and the executor together. A preparation failure prevents either service from starting.
5. Bootstrap with `docker compose exec web python manage.py createsuperuser`. Check the HTTPS certificate chain, secure cookies, login behavior, and authorized scopes before adding devices.
6. Run `docker compose exec web python manage.py check --deploy`. HSTS preload is intentionally not enabled: domain-wide preload enrollment is a deployment decision.

SQLite is the deliberate MVP constraint: short transactions, a 20-second busy timeout, two web workers, and exactly one executor. Scale or move to PostgreSQL only after measuring write contention; never scale executor replicas with this configuration. External administrator changes can still race group writes when conditional updates are unavailable.

No production deployment or device mutation has been performed by this implementation session. Container build/runtime and TLS behavior must be verified on the target host.

## Runtime, permissions, and logs

The application image runs as UID/GID `10001:10001`; application code is read-only to that user. Only `data/` and `staticfiles/` need writes. New named static volumes inherit the image directory ownership; existing volumes may need ownership correction before startup. Secret files must be readable by UID 10001. The Nginx proxy runs unprivileged and listens on container ports 8080/8443, mapped to host ports 80/443; TLS files must be readable by its UID 101. Keep secret files protected on the host while granting the necessary container readers. Bind-mounted file permissions are not automatically fixed by the image.

Tini forwards shutdown signals and reaps child processes. The application supervisor stops the surviving service and exits with an error if either Gunicorn or the runner exits unexpectedly, including a zero exit status. Compose restarts the combined container. On normal shutdown both receive termination, with a bounded 30-second shutdown wait and a 45-second Compose grace period. Do not scale `web`: each replica would include another executor, and this SQLite deployment supports one application container.

Both child processes inherit stdout and merge stderr into stdout. Gunicorn access/error logs, runner results and tracebacks, startup messages, and application audit logs are visible together:

```sh
docker compose logs -f web
docker compose logs -f proxy
docker compose restart web
```

Access logs omit query strings to avoid logging OIDC authorization codes. Do not enable debug logging of credentials or HTTP payloads. Configure Docker log rotation/retention on the host. Nginx also sends access and error logs to stdout.

After an interrupted execution, inspect uncertain requests and reconcile observed firewall state. The singleton runner lease may delay recovery until its five-minute expiry; do not remove leases or replay requests to force a restart. Stop the previous runtime before recovery.

To replace an older deployment with a separate executor service, use `docker compose up --build -d --remove-orphans` so the old runner container is removed. Stop the old stack first to avoid overlapping executors. Local development still uses `runserver` and `run_executor` in separate terminals; `runserver` alone never executes approved requests.

## Runtime and dependency versions (2026-10-24)

The application image uses Python 3.14.9 and the asset builder uses Node.js 26.12.1 / npm 12.2.1. Django is 6.1.2. Python 3.15.0 is newer, but Django documents Python 3.15 support starting with 6.1.3; keep production on Python 3.14 until that stable dependency is available and verified.

Production Python dependencies, including transitive dependencies, are pinned in `requirements.lock`; Docker installs with that constraint file. Frontend packages are pinned through `package-lock.json`. To refresh Python dependencies deliberately, run `uv pip compile pyproject.toml --universal --python-version 3.14 --upgrade --output-file requirements.lock`, then run the full test suite and rebuild the image. Use `docker compose build --pull` and `docker compose pull proxy` to refresh base/proxy images; rebuild and validate before deployment. The Nginx image remains on the latest stable unprivileged Alpine track.

Back up the database, uploaded files, deployment configuration, and encryption keys before replacing an existing runtime. Major library upgrades require applying migrations with the new runtime; the production launcher does this before starting either process.

OIDC accepts a small clock difference for token issued-at and not-before claims: `OIDC_CLOCK_SKEW_SECONDS` defaults to 60, with an allowed range of 0–120 seconds. Expired tokens remain rejected. Keep the app host and identity provider synchronized with NTP; larger drift must be fixed on the hosts. Invalid tokens produce a controlled rejection instead of a callback traceback. After a failed callback, start a new login rather than reusing its one-time authorization code.
