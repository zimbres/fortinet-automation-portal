# Local Catalog and Firewall Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manage objects and address groups locally, import objects in batches, and independently approve installation on one firewall or a firewall group.

**Architecture:** Extend the existing Django monolith with a local catalog and separate installation request models. Preserve legacy change requests and share the single executor lease; immutable installation snapshots drive per-destination execution. Catalog, import, target resolution, approval, execution, and presentation have separate service modules.

**Tech Stack:** Django 5.2, SQLite, Python 3.12/3.13, templates/HTMX, Tailwind CSS, HTTPX, pytest, existing Postman HTTP simulation.

**Spec:** `docs/superpowers/specs/2026-10-23-local-catalog-installation-design.md` (approved by the user on 2026-10-23).

## Global Constraints

- Application UI and documentation remain in English.
- Catalog CRUD, group membership edits, and bulk import are local transactions with audit records and no firewall HTTP calls.
- Limit each batch to 1,000 rows and 1 MiB input.
- A group has at most one selected VDOM per firewall in this increment.
- Administrative status never bypasses independent approval.
- No database transaction remains open across network I/O.
- Do not enable real device writes as part of this feature.
- Preserve existing requests, credentials, grants, audit records, and inventory observations.
- No new public JSON API or extra infrastructure is required.

## Review Focus

1. Concurrent object/group naming collisions must fail atomically across their shared namespace (Task 1).
2. Quoted CSV newlines, BOMs, malformed encoding, and preview tampering must preserve row interpretation and create nothing on errors (Task 2).
3. A user with access to only some destinations must not discover the remaining destination names through lists, detail URLs, or approval queues (Tasks 3, 7).
4. Definition edits during snapshot assembly must not produce mixed revisions in an approved request (Task 4).
5. Executor restart between targets must preserve completed steps without replaying writes or silently skipping pending targets (Task 6).

## File and model boundaries

- `apps/inventory/models.py`: add CatalogEntry (unique shared name, entry_type, revision, creator/updater, timestamps), AddressObject (one-to-one entry, kind, value), AddressGroup (one-to-one entry, explicit object membership), and CatalogImport (UUID token, actor, normalized rows/digest, expiry, completion). Keep InventoryScan unchanged. Shared names live in one table for database-enforced uniqueness.
- `apps/inventory/catalog.py`, `imports.py`, `forms.py`: local CRUD, CSV preview/confirmation, and form validation respectively.
- `apps/accounts/models.py`, `permissions.py`, `admin.py`, `forms.py`: CatalogGrant with unique user/capability and grant-management UI. Keep ScopeGrant semantics.
- `apps/firewalls/models.py`, `groups.py`, `forms.py`: FirewallGroup and FirewallGroupMember(group, firewall, vdom); unique group/firewall and group/vdom. Services validate that vdom.firewall_id equals firewall_id.
- `apps/changes/models.py`: separate InstallationRequest, InstallationTarget, InstallationStep, InstalledResource. Retain legacy models unchanged. Targets hold VDOM FK and immutable destination snapshot; resources use unique VDOM/resource_type/name and originating target.
- `apps/changes/installations.py`, `installation_executor.py`, `installation_reconciliation.py`: new request lifecycle, per-target writes, and read-only reconciliation. Reuse lease/auth/audit/adapter primitives, not legacy payload interpretation.
- `apps/portal/catalog_views.py`, `installation_views.py`, `firewall_group_views.py`: new focused handlers. Keep `views.py` for legacy request details/decisions, device inventory, and existing administration.
- `templates/portal/catalog_*.html`, `installation_*.html`, `firewall_groups.html`: new screens using existing base/forms/tables and design tokens.
- Generate additive migrations in accounts, inventory, firewalls, and changes; do not hand-edit existing migrations.

All service functions below are keyword-only; IDs are integers except request/import UUIDs. Validation raises Django ValidationError and authorization raises PermissionDenied. Serializers produce JSON-compatible values and never include credentials.

### Task 1: Local catalog, permissions, and safe mutations

**Files:** Modify inventory/models.py; accounts/models.py, permissions.py, admin.py. Create inventory/catalog.py, corresponding migrations, tests/test_catalog.py.

**Interfaces:** `require_catalog_capability(user, capability: str) -> None`; `save_address(*, actor, name: str, kind: str, value: str, entry_id: int | None = None, expected_revision: int | None = None) -> AddressObject`; `save_address_group(*, actor, name: str, member_ids: list[int], entry_id: int | None = None, expected_revision: int | None = None) -> AddressGroup`; `delete_catalog_entry(*, actor, entry_id: int, expected_revision: int) -> None`. New entries start at revision 1; successful edits increment it. IDs in member_ids refer to AddressObject primary keys.

- [ ] Write tests `test_catalog_requires_explicit_global_grant`, `test_manage_includes_view_and_superadmin_can_manage`, `test_local_crud_audited_without_requests_or_http`, `test_stale_revision_rejected`, `test_referenced_object_delete_blocked`, `test_shared_namespace_collision_rolls_back`. Assert no ChangeRequest or InstallationRequest is created; mock the adapter constructor only to assert zero calls. Use two attempted creates against the shared unique entry name and verify one committed entry with no orphan detail rows.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py -q`; confirm failures correspond to missing functionality.
- [ ] Implement models/grants/services with existing validators, canonical subnet values, transactions, revision compare-and-update, protected memberships, and audit events. Generate migrations; do not assign new grants to ordinary users implicitly.
- [ ] Run the task tests and existing access tests; require all passing. Check generated constraints support case-sensitive shared names and unique grants.
- [ ] Commit only Task 1 files: `feat: persist local address catalog with explicit access`.

### Task 2: Atomic object import with preview

**Files:** Create inventory/imports.py; extend inventory/models.py and migrations; create tests/test_catalog_import.py.

**Interfaces:** `preview_import(*, actor, content: bytes) -> CatalogImport`; `confirm_import(*, actor, token: UUID) -> list[AddressObject]`. A preview stores normalized rows and structured row errors; previews with errors cannot confirm. UTF-8-sig decoding and csv.DictReader implement the exact name,kind,value header contract. Store a content digest, server-side actor binding, and 30-minute expiry; only server-stored rows drive confirmation. Completed tokens return the original object list without creating or auditing duplicates; check actor access first.

- [ ] Write `test_valid_batch_creates_all_once`, `test_invalid_batch_creates_zero`, `test_limit_1000_rows_and_1_mib`, `test_preview_expiry_actor_binding_and_tampering`, `test_confirm_revalidates_collision_and_revoked_grant`, `test_bom_quoted_newlines_bad_utf8_and_extra_cells`. Assert accepted/rejected boundaries at 1,000/1,001 rows and 1,048,576/1,048,577 bytes; row errors identify parsed CSV record numbers. Pasted strings are UTF-8 encoded before size validation.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_catalog_import.py -q`; observe behavioral failures.
- [ ] Implement bounded parsing, full-batch validation, server-side previews, atomic confirmation claim, create-only writes, and batch audit. Reuse Task 1 validation; protect confirmed entry references so repeat confirmation remains defined.
- [ ] Rerun import and catalog tests; require all passing, including duplicate token and confirmation collision rollback.
- [ ] Commit Task 2 files: `feat: preview and atomically import address lists`.

### Task 3: Firewall groups and explicit target authorization

**Files:** Modify firewalls/models.py, forms.py; create firewalls/groups.py, migration, tests/test_firewall_groups.py.

**Interfaces:** `save_firewall_group(*, actor, name: str, vdom_ids: list[int], group_id: int | None = None, enabled: bool = True) -> FirewallGroup`; `visible_firewall_groups(user, capability: str = 'view') -> QuerySet`; `resolve_destinations(*, actor, target_kind: str, vdom_id: int | None = None, firewall_group_id: int | None = None) -> list[VDOM]`. Return deterministic destination order by VDOM primary key. target_kind is firewall or firewall_group and exactly its matching ID is allowed.

- [ ] Write tests for superadministrator-only mutations, mismatched firewall/VDOM rejection, unique firewall per group, empty/disabled targets, all-member authorization, ambiguous target IDs, and `test_partial_scope_user_cannot_discover_group`. Assert no group label/member names are returned to a partial-scope user.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_firewall_groups.py -q`; observe failures.
- [ ] Implement models, constrained membership services, atomic membership replacement and audit, filtered querysets, and target resolution. Keep visibility strict even when only some members are enabled.
- [ ] Rerun task and existing access tests; require all passing.
- [ ] Commit Task 3 files: `feat: resolve authorized firewall group destinations`.

### Task 4: Immutable installation requests and independent approval

**Files:** Modify changes/models.py; create changes/installations.py, migration, tests/test_installations.py.

**Interfaces:** `submit_installation(*, actor, object_ids: list[int], group_ids: list[int], target_kind: str, vdom_id: int | None = None, firewall_group_id: int | None = None, idempotency_key: str) -> InstallationRequest`; `decide_installation(*, actor, request_id: UUID, status: str) -> InstallationRequest`; `installations_for(user, capability: str = 'view') -> QuerySet`; `check_installation_authorization(target: InstallationTarget) -> None`; `refresh_installation_status(request_id: UUID) -> InstallationRequest`.

- [ ] Write tests for dependency inclusion/deduplication, definition/target edits after submission, deletion with snapshot retention, self-approval, every-destination approval, revoked identities/grants, conflicting idempotency, atomic decisions, and `test_snapshot_assembly_never_mixes_revisions`. Assert snapshot/digest cannot be saved with altered intent and failed assembly creates no parent/targets. Use the transaction/revision check at the assembly boundary to reproduce an edit.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_installations.py -q`; confirm failures.
- [ ] Implement separate installation schema, canonical snapshot serialization/digest, protected target FKs, snapshot construction within one short atomic transaction, and conditional status transitions. Snapshot selected catalog entries and required dependencies; keep FK provenance optional for deletable definitions. Cancellation requires requester and PENDING approval/execution. Decision statuses are APPROVED, REJECTED, CANCELLED only.
- [ ] Implement all-target visibility with no partial request leakage. Define parent reduction in order: any RUNNING -> RUNNING while active processing; after processing any uncertain -> RECONCILIATION_REQUIRED; all success -> SUCCEEDED; all failed -> FAILED; terminal success/failure mix -> PARTIALLY_SUCCEEDED; remaining pending -> PENDING before start or RUNNING after start. Preserve uncertainty precedence once processing has stopped.
- [ ] Rerun installation, legacy changes, and access tests; require all passing and legacy digest unchanged.
- [ ] Commit Task 4 files: `feat: snapshot and approve multi-destination installations`.

### Task 5: Verified per-target installation

**Files:** Create changes/installation_executor.py; modify fortinet/client.py, capabilities.py; create tests/test_installation_execution.py.

**Interfaces:** `preflight_installation(target: InstallationTarget, client: FortinetClient) -> dict`; `execute_installation_target(*, target_id: int, owner_id: str) -> InstallationTarget`; adapter `create_group(payload: dict) -> dict | None`. Reuse existing address create/update/group member methods. New operation capability names: install_address, create_group, install_group_members. Production VALIDATED_WRITE_PROFILES stays empty.

- [ ] Write tests for full-target preflight before writes, dependency order, exact existing address no-op/no ownership adoption, changed owned address update, unowned conflict, protected namespace, allowed-group checks, missing group capability, additive preserved members, permission rechecks before each write, malformed readback, and partial target failure. Verify every write has a matching step and uncertain outcomes never become FAILED solely because readback failed.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_installation_execution.py -q`; observe failures.
- [ ] Implement preflight and ordered mutations against immutable snapshots with lease heartbeat, grant/digest checks, ownership records, readback verification, and sanitized outcome persistence. Preflight validates all dependencies including conflicts before first write; refresh live group membership immediately before modification. Do not hold transactions over client calls. Reuse legacy ObjectReference ownership when evaluating existing portal-owned addresses, without changing its provenance.
- [ ] Rerun task, existing adapter, and legacy execution tests; require all passing. Confirm production write profiles remain empty.
- [ ] Commit Task 5 files: `feat: verify ordered object and group installations per target`.

### Task 6: Shared executor scheduling and read-only recovery

**Files:** Modify changes/executor.py, management/commands/run_executor.py, management/commands/reconcile_requests.py; create changes/installation_reconciliation.py, tests/test_installation_reconciliation.py; extend execution tests.

**Interfaces:** Preserve `execute_next(*, owner_id: str)` as scheduler returning either legacy ChangeRequest, InstallationRequest, or None. Extract the existing legacy execution body to `execute_legacy_next(*, owner_id: str)` if needed without changing its behavior. Add `execute_next_installation(*, owner_id: str) -> InstallationRequest | None`; `reconcile_installation(*, actor, request_id: UUID) -> InstallationRequest`. Both queues use the same lease; scheduler chooses oldest eligible creation time across queues to avoid starvation.

- [ ] Write tests for mixed queues sharing one lease, continuation after proven target failure, independent targets after uncertainty while lease is valid, parent aggregation, `test_restart_between_targets_does_not_replay`, lease loss, and read-only reconciliation. Assert zero POST/PUT/DELETE during reconciliation and preserved successful target/step IDs.
- [ ] Run task tests and legacy executor/reconciliation tests; observe new-test failures before implementation.
- [ ] Implement atomic parent/target claims and recovery. Lease expiry marks abandoned RUNNING installations as requiring reconciliation, including a parent abandoned between targets. Persist a recovery-required marker to distinguish lease recovery from an isolated uncertain target. Reconciliation checks all interrupted/uncertain targets against saved intent and step evidence; mark confirmed targets SUCCEEDED, leave unresolved targets uncertain. Clear the recovery marker only when interrupted outcomes are established, allowing previously untouched PENDING targets to run with existing approval and fresh authorization. Failed targets require a new request; completed targets never replay.
- [ ] Rerun new and legacy lifecycle suites; require all passing with reconciliation state reported per target.
- [ ] Commit Task 6 files: `feat: recover multi-target installations without replaying writes`.

### Task 7: Catalog, firewall-group, and installation portal flows

**Files:** Create focused portal/catalog_views.py, installation_views.py, firewall_group_views.py and inventory/forms.py; modify changes/forms.py, firewalls/forms.py, accounts/forms.py/admin.py, portal/views.py, config/urls.py, templates/base.html and portal dashboard/history/users templates; create catalog_*.html, installation_*.html, firewall_groups.html; create tests/test_catalog_views.py, tests/test_installation_views.py; update tests/test_views.py.

**Interfaces/routes:** Preserve /objects/ and /groups/ as catalog lists; add /objects/new/, /objects/<int:pk>/edit/, /objects/<int:pk>/delete/, /objects/import/, /objects/import/<uuid:token>/confirm/, /objects/import/example.csv, matching group CRUD, /firewall-groups/ CRUD, /installations/<uuid:pk>/ detail and /installations/<uuid:pk>/<str:action>/ decisions. /requests/new/ submits installations; existing /requests/<uuid:pk>/ routes remain legacy. Move former remote inventory to /device-inventory/ with explicit VDOM/source labels. Mutations are POST-only with CSRF. Example CSV is read-only and requires catalog view.

- [ ] Write view tests for persisted catalog lists with adapter unreachable, CRUD/import preview/confirmation, explicit VDOM and target selection, catalog grant administration restricted to superadministrators, snapshot/dependency preview, independent approval, per-target results, POST/CSRF enforcement, legacy details/history, and `test_partial_scope_user_cannot_discover_installation_via_detail_queue_or_dashboard`.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_catalog_views.py tests/test_installation_views.py tests/test_views.py -q`; observe new-flow failures.
- [ ] Implement forms/views/templates using Tasks 1–6 services. New-request preview uses the same normalized snapshot builder as submission and revalidates at submit; submitted details show the immutable result. Display additive member installation explicitly. History/dashboard combine authorized legacy and installation records, identify request kind, and expose separate catalog counts; queries must not leak hidden targets. Catalog deletion uses a confirmation page; local-only labels explain no device removal.
- [ ] Run view/access tests and `npm run build`; require passing tests/build. Inspect changed flows at desktop and 390px mobile with real local test records, keyboard focus, error messages and row previews. Load applicable interface/computer-use skills at execution time. Fix findings together and perform one confirmation pass.
- [ ] Commit Task 7 files including rebuilt static/app.css: `feat: expose local catalog and approved installation workflows`.

### Task 8: HTTP simulation, upgrade verification, and documentation

**Files:** Modify postman/mocks/fortinet/default.js, config.yaml and simulation yaml only as needed; create tests/integration/test_installation_flow.py and tests/test_catalog_migrations.py; update PRODUCT.md, README.md, docs/testing.md, operations.md, development-ledger.md and the specification approval status.

**Interfaces:** Reuse FORTINET_SIMULATION_URL and the existing test-only HTTP transport. Mock state must isolate destinations using test firewall identity/VDOM, not collapse multiple targets into one device. Load postman:api-simulation before changing/running simulation; keep work local with no workspace publication.

- [ ] Add real-client HTTP scenarios for multi-target success, group creation/dependency order, identical address no-op, unowned conflicts, preserved unrelated members, explicit failure on one target, uncertain write/readback, and read-only reconciliation. Add a MigrationExecutor test upgrading populated old migrations to current: assert original users, grants, requests/digests, provenance, credentials and audit survive, and the catalog is empty.
- [ ] Run targeted new tests against the local simulator and observe failures before implementing missing mock behavior. Extend only the test contract and simulation profiles; production capability gates stay disabled.
- [ ] Run the simulator using documented local port 4900 and the complete suite with FORTINET_SIMULATION_URL configured. Require all tests passing with no HTTP-scenario skips; inspect simulator events for actual destination-specific client calls. Stop the temporary simulator after verification.
- [ ] Run `.venv/Scripts/python.exe manage.py check`, `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`, `npm run build`, and `git diff --check`; require success. Rehearse fresh migrations on an isolated SQLite database, never reset the user's existing DB. Migration tests establish upgrade preservation; record actual commands/results.
- [ ] Update product/operations docs to explain local authority, independent catalog grants, CSV limits/expiry, explicit VDOM mapping, additive group installation, snapshots, partial outcomes, recovery, retained legacy requests, and unvalidated real-device capability profiles. Mark the approved spec as approved without altering its requirements.
- [ ] Commit Task 8 files: `test: validate catalog upgrade and multi-firewall installation flows`.

## Self-review and execution handoff

Coverage checked: catalog and grants (1), import (2), firewall groups (3), immutable intent/approval and status reduction (4), target writes/provenance/capabilities (5), shared scheduling and recovery (6), UI/observations (7), migration and integration evidence/docs (8). The five Review Focus conditions have named tests in their owning tasks. Legacy APIs remain callable; new installation models avoid rewriting historical digests. No implementation or test execution is claimed by this plan.

Recommended execution method: Native, with sequential tasks in this session and a final independent review. Tasks share schema, permission, and scheduler interfaces, so keeping implementation context together reduces handoff overhead. User review of this plan and selection of execution method are required before implementation. Load using-git-worktrees at execution time; preserve existing local data and running processes, and inspect current attachments/state before choosing an isolated checkout. Record verification and any deviations in the development ledger.
