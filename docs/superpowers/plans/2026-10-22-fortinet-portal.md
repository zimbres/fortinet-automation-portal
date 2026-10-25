# Fortinet Automation Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved internal portal with independently approved firewall changes, verified execution, encrypted credentials, and audit history.

**Architecture:** Modular Django monolith with server-rendered pages and a single database-coordinated execution process. FortiGate remains authoritative; approval and execution are separate lifecycles. Local HTTP simulation precedes any device validation.

**Tech Stack:** Django 5.2 LTS, SQLite, HTMX, Tailwind CSS, HTTPX, cryptography, mozilla-django-oidc, Gunicorn, Nginx, Docker Compose, pytest-django.

**Spec:** `docs/superpowers/specs/2026-10-22-fortinet-portal-design.md`

**Execution record:** The direct implementation and its verification/deviations are recorded in `docs/development-ledger.md`. The checklist below preserves the original plan; use the ledger for actual status and version-dependent limitations.

## Global Constraints

- Write the application and all project documentation in English.
- Use a modular Django 5.2 LTS monolith with server-rendered templates, HTMX, compiled Tailwind CSS, SQLite, HTTPX, and Python ipaddress.
- React, Redis, and Celery are excluded from the MVP.
- The same identity may never approve its own request.
- No browser receives firewall credentials or calls a firewall directly.
- Permit writes only for explicitly validated version/capability profiles.
- No live firewall mutation is part of initial local verification.
- The requesting user must never approve their own request, including users with elevated roles.
- Inspect the interface once across desktop and mobile, fix findings together, and perform at most one confirmation pass.

## Review Focus

- Approval followed by account suspension or scope revocation must block execution: Task 5/6.
- A write accepted by Fortinet followed by a broken response must not trigger a duplicate write: Task 6.
- An object created successfully before group update failure must remain visible as partial completion: Task 6.
- Unknown versions, partial policy inventory, and unsupported reference constructs must fail conservatively: Tasks 4/7.
- Credentials must remain absent from validation errors, HTTP exceptions, audit snapshots, and HTML: Tasks 3/8.

## File boundaries and conventions

`config/settings/{base,development,production}.py` owns environment configuration. `apps/accounts` owns users, OIDC, and authorization; `apps/firewalls` owns inventory and encrypted device configuration; `apps/fortinet` owns remote contracts and HTTP; `apps/changes` owns lifecycle and execution; `apps/audit` owns event persistence; `apps/inventory` owns usage scans. Each app has separate models, services, views, URLs, and tests where relevant. Templates live under `templates/<app>/`; compiled CSS and vendored HTMX under `static/`. Never create a top-level package named requests.

Use `.venv` and `python -m pytest` with `DJANGO_SETTINGS_MODULE=config.settings.development`. All task verification commands run in the project root. Install dependencies only during execution. The directory currently has no Git repository: establish local Git tracking at execution start, preserve existing files, and commit completed tasks locally without pushing.

### Task 1: Runnable foundation and audit persistence

**Files:** `manage.py`, `pyproject.toml`, `config/settings/*.py`, `config/urls.py`, `config/wsgi.py`, `apps/*/__init__.py`, `apps/*/apps.py`, `apps/accounts/models.py`, `apps/audit/{models,services}.py`, initial migrations, `.gitignore`, `.env.example`, `tests/test_foundation.py`.

**Interfaces:** custom `accounts.User(AbstractUser)` with external issuer/subject uniqueness; `audit.record_event(*, actor, event_type: str, request=None, metadata: dict) -> AuditEvent`. Audit metadata is sanitized before persistence.

- [ ] Write `test_empty_database_migrates`, `test_external_identity_pair_is_unique`, and `test_audit_has_no_update_delete_application_api`; assert migration success, duplicate rejection, and append-only service behavior.
- [ ] Run `python -m pytest tests/test_foundation.py -q`; confirm failure before implementation.
- [ ] Create the Django skeleton, dependency declarations, custom user, audit model/service, settings, and initial migrations. Keep dependency versions within supported release lines and record resolved versions.
- [ ] Run `python manage.py migrate`, `python manage.py check`, and the task tests; require successful migration, no check errors, and passing tests. Commit the foundation.

### Task 2: Provisioned identity and scoped access

**Files:** `apps/accounts/{permissions,services,oidc,views,urls,admin}.py`, account migration updates, `tests/test_accounts.py`.

**Interfaces:** `require_capability(user, vdom, capability: str) -> None`; `provision_user(*, actor, username: str, role_names: list[str]) -> User`. Capabilities: view, submit, approve, administer; only Superadministrator provisions users or changes roles.

- [ ] Write tests asserting foreign-VDOM denial, inactive-user denial, superadministrator-only provisioning, issuer/subject binding, no OIDC auto-provisioning, and no role elevation from untrusted claims.
- [ ] Run `python -m pytest tests/test_accounts.py -q`; confirm expected failures.
- [ ] Implement role presets, scoped grants, explicit local/OIDC authentication settings, bootstrap administration, login event auditing, and strict provisioned-account OIDC mapping.
- [ ] Run account tests and Django checks; require passing results. Commit scoped authentication.

### Task 3: Firewall registration and encrypted secrets

**Files:** `apps/firewalls/{models,crypto,forms,services,admin}.py`, migrations, `tests/test_firewalls.py`, `.env.example`.

**Interfaces:** `encrypt_secret(value: str) -> str`, `decrypt_secret(value: str) -> str`; Firewall and VDOM models; `register_firewall(*, actor, name, hostname, port, token, allowed_namespace) -> Firewall`. ScopeGrant references VDOM through a lazy model relation.

- [ ] Write tests proving ciphertext differs from token, decryption round-trips, previous keys remain readable during rotation, missing keys fail closed, VDOM names are unique per firewall, and secrets are absent from repr/errors/audit metadata.
- [ ] Run `python -m pytest tests/test_firewalls.py -q`; confirm expected failures.
- [ ] Implement authenticated field encryption with versioned external key configuration, encrypted API tokens, write-only secret forms, endpoint validation, namespace configuration, and audited administration.
- [ ] Run task tests; require all passing. Commit encrypted firewall configuration.

### Task 4: Fortinet contract and adapter

**Files:** `apps/fortinet/{client,schemas,addresses,groups,references,capabilities,exceptions}.py`, `contracts/fortinet.md`, `tests/test_fortinet.py`, `tests/fixtures/fortinet/`.

**Interfaces:** `FortinetClient(firewall, vdom)` with `list_addresses()`, `get_address(name)`, `create_address(payload)`, `update_address(name, payload)`, `delete_address(name)`, `list_groups()`, `get_group(name)`, `set_group_members(name, members)`, and `get_reference_report(name)`. Return typed normalized records; `ReferenceReport.complete` gates deletion. `require_write_capability(version, operation)` rejects unvalidated profiles.

- [ ] Use Postman api-discovery for current vendor contract discovery before adapter implementation. Record primary evidence for authentication, endpoints, reference inspection, FQDN/wildcard payloads, pagination, and conditional-write support; mark unverified features unavailable.
- [ ] Write adapter tests for each address type, escaped names, VDOM selection, pagination, preserved group members, redirects disabled, invalid TLS, FortiOS failure bodies, invalid JSON, timeouts, and unknown-version write rejection.
- [ ] Run `python -m pytest tests/test_fortinet.py -q`; confirm expected failures.
- [ ] Implement normalized validation, bounded verified HTTPS calls, sanitized exceptions, explicit capability profiles, reference completeness, and local contract fixtures. Reject IPv6 for this MVP.
- [ ] Run adapter tests; require passing results. Commit adapter and evidence. No actual version profile becomes validated solely because a mock passes.

### Task 5: Immutable requests and independent approval

**Files:** `apps/changes/{models,schemas,services}.py`, migrations, `tests/test_changes.py`.

**Interfaces:** `submit_change(*, actor, vdom, operation: str, payload: dict, idempotency_key: str) -> ChangeRequest`; `approve_change(*, actor, request_id) -> ChangeRequest`; `reject_change(*, actor, request_id, reason: str) -> ChangeRequest`; `cancel_change(*, actor, request_id) -> ChangeRequest`.

- [ ] Write tests asserting self-approval fails even for Superadministrator, wrong-scope approval fails, approved payloads cannot change, identical idempotent submissions return one request, conflicting key reuse fails, and rejected/cancelled requests cannot become executable.
- [ ] Run `python -m pytest tests/test_changes.py -q`; confirm expected failures.
- [ ] Implement separate approval/execution fields, canonical payload digest, atomic transitions, scoped checks, uniqueness constraints, and audited actor identities. Editing submitted intent requires a new request.
- [ ] Run task tests, including concurrent approval attempts and revoked approver/requester checks; require passing results. Commit approval lifecycle.

### Task 6: Single executor and verified reconciliation

**Files:** `apps/changes/{executor,reconciliation,lease}.py`, `apps/changes/management/commands/{run_executor,reconcile_requests}.py`, model migrations, `tests/test_execution.py`.

**Interfaces:** `execute_next(*, owner_id: str) -> ChangeRequest | None`; `reconcile_change(*, actor, request_id) -> ChangeRequest`. Database lease ownership/heartbeat permits one executor; network calls occur outside database transactions.

- [ ] Write tests covering atomic claiming, a second executor refusal, expired lease recovery without replay, permission revocation after approval, protected namespace, reference-check deletion refusal, read-back mismatch, partial create-and-add failure, and write timeout with no retry.
- [ ] Run `python -m pytest tests/test_execution.py -q`; confirm expected failures.
- [ ] Implement operation dispatch, revalidated permissions and prerequisites, step records, before/after observations, group conflict detection, and success only after verification. Reconciliation is read-only; unresolved state stays RECONCILIATION_REQUIRED. Proven partial failures retain created objects.
- [ ] Run execution tests with independent database connections where concurrency matters; require passing results. Commit executor and reconciliation.

### Task 7: Conservative unused-object scans

**Files:** `apps/inventory/{models,services,usage}.py`, migrations, `tests/test_usage.py`.

**Interfaces:** `scan_usage(*, actor, vdom) -> InventoryScan`; `classify_usage(addresses, groups, policies, *, complete: bool) -> dict[str, str]`, returning used, potentially_unused, or unknown.

- [ ] Write tests for direct usage, nested groups, cycles, wildcard/all references, pagination, unsupported policy constructs, and incomplete scans; assert incomplete evidence never produces a definitive unused verdict.
- [ ] Run `python -m pytest tests/test_usage.py -q`; confirm expected failures.
- [ ] Implement on-demand scoped scans, timestamped coverage, conservative classifications, and audited results. No deletion side effects.
- [ ] Run usage tests; require passing results. Commit inventory assessment.

### Task 8: Complete portal interface

**Files:** `templates/base.html`, `templates/{accounts,firewalls,inventory,changes,audit}/*.html`, corresponding app `{forms,views,urls}.py`, `static/src/app.css`, Tailwind build configuration, vendored HTMX, `tests/test_views.py`.

**Interfaces:** named routes for dashboard, firewalls, objects, groups, new request, approvals, request detail, history, unused objects, and user management. Views consume the services defined in prior tasks; POST requests perform mutations and require CSRF.

- [ ] Before UI edits, read Impeccable new-work and craft-floor and establish a code-first Operate surface direction using approved product context.
- [ ] Write view tests for server-side authorization, CSRF, English validation/copy, forged hidden scope fields, escaping hostile names, secret-free HTML, empty states, and absence of self-approval controls alongside service enforcement.
- [ ] Run `python -m pytest tests/test_views.py -q`; confirm expected failures.
- [ ] Implement responsive navigation, labeled forms, real dashboard counts, explicit existing/create object selection, approval diffs, execution steps, filters, and accessible textual status. Compile and serve local CSS/JS.
- [ ] Run view tests and production asset build; inspect desktop/mobile together, fix findings in one batch, confirm once. Commit interface.

### Task 9: Running HTTP simulation and integration failures

**Files:** `tests/integration/test_portal_flow.py`, local Postman simulation artifacts selected by api-simulation, `docs/testing.md`.

**Interfaces:** the real Django application and executor call a local HTTP Fortinet stand-in through an explicitly test-only endpoint configuration; production remains HTTPS-only.

- [ ] Load Postman api-simulation and configure a local environment without publishing shared resources. Reuse Task 4 contracts and fixtures.
- [ ] Write integration assertions: submit as Operator, approve as another scoped user, execute, verify mock state and audit; repeat for timeout-after-apply, rejection, concurrent external group change, and partial completion.
- [ ] Run the new scenarios before integration fixes; record failures against the actual running application, not just patched adapter methods.
- [ ] Resolve integration defects and rerun scenarios; require matching database, audit, and remote observed state. Document simulated versus live coverage and remaining FortiOS version limitations. Commit integration evidence.

### Task 10: Deployment, operations, and final verification

**Files:** `docker/Dockerfile`, `docker/nginx.conf`, `compose.yaml`, `README.md`, `docs/{deployment,backup-restore,security,operations}.md`, `.env.example`, deployment tests.

**Interfaces:** Compose web/executor/proxy services share a local SQLite data volume; keys are mounted separately. Management commands bootstrap the administrator, run reconciliation, and support controlled credential rotation.

- [ ] Write checks for missing production secrets, secure session settings, invalid host configuration, multiple executor ownership, and backup/restore consistency; require failure for unsafe configuration.
- [ ] Implement container build, TLS proxy configuration, health checks, production checks, local-volume permissions, documented restore rehearsal, rotation procedure, and start/stop instructions. Do not commit real secrets or certificates.
- [ ] Run `python -m pytest -q`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, asset build, clean-database migration, production deployment checks with test secrets, and `docker compose config`. Run container startup and restore rehearsal if Docker is available; disclose unavailable checks.
- [ ] Use requesting-code-review and verification-before-completion before claiming completion. Fix material findings, rerun affected checks, commit, and provide launch instructions and exact tested limitations. Do not push, publish, or mutate real firewalls.
