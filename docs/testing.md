# Testing and integration evidence

New catalog tests cover explicit global grants, local-only mutations, shared object/group names, stale revisions, import preview/confirmation, firewall-group target resolution, immutable installation intent, all-destination approval/visibility, target execution, recovery, and populated legacy schema upgrades. `tests/integration/test_installation_flow.py` runs seven destination-isolated HTTP scenarios using the real client and executor. The test-only transport identifies mock destinations with `x-test-device`; no production header or endpoint is changed. See `docs/local-catalog.md` for the changed product contract.

Verification on 2026-10-23: 123 passed in 160.57 seconds with the simulation configured, with no skips. The suite includes regressions for destination disabling, opposite-resource namespace collisions, changed no-op addresses, recreated-group provenance, view/action permission intersections, and interrupted multi-target recovery. Desktop catalog/import and mobile installation preview were inspected against isolated local fixtures; an action-button overflow was corrected and confirmed. These results cover local/simulated behavior, not actual FortiOS compatibility.

Run `.venv/Scripts/python.exe -m pytest -q` for the local suite. Temporary files stay inside `.cache/pytest`. HTTP simulation tests are skipped unless their endpoint is explicitly configured.

The repository includes a local Postman stateful Fortinet stand-in derived from the supplied architecture and documented partial vendor contract. Owner workspace search was skipped because no organization workspace was provided; this mock is not a vendor-certified API implementation.

```powershell
postman simulation run postman/simulations/fortinet.sim.yaml --port 4900 --output ndjson
```

In a second terminal:

```powershell
$env:FORTINET_SIMULATION_URL='http://127.0.0.1:4900/fortinet'
.venv/Scripts/python.exe -m pytest -q
```

The real Django services, database lifecycle, executor, and HTTPX client run against local HTTP. A test-only transport rewrites HTTPS device requests to the local simulator; configured firewall HTTP/HTTPS selection is preserved before the test-only routing override. Tests replace the write-capability gate only inside the test process; the live-validated profile remains restricted to its exact device scope. They cover success, explicit rejection, uncertain write outcome, post-write read failure, partial completion, concurrent group changes, and invalid target groups. Simulator request events confirm that the HTTP dependency was exercised; simulation logs are not committed.

The `uncertain` scenario applies a mutation then returns HTTP 500. A separate transport-level unit test covers an actual HTTPX timeout exception. Do not describe the HTTP-500 scenario as a real hanging TCP request.

Browser checks cover the real dashboard and request form at desktop and 390px mobile widths. Visual captures use the current empty database state, not fabricated counters. Scoped access, CSRF, external identity binding, encryption rotation, independent approval, idempotency, lease recovery, and conservative usage classification have automated coverage.

The Docker image was built successfully. An isolated container passed production settings checks, clean-database migrations, static collection, and one-shot executor startup. The production check reports W021 because HSTS preload is intentionally not enabled.

Still unverified: actual FortiOS compatibility, authoritative deletion references, external-administrator write atomicity, a configured live OIDC provider, full target-host Compose/Nginx TLS behavior, and external protected log export. No live FortiGate was changed.

Firewall configuration tests also exercise a real local HTTP server and a local TLS server with a generated self-signed certificate, using the production FortinetClient directly. Form tests cover protocol defaults, custom ports, API Token preservation, removed Login/Allowed groups fields, and the Object name prefix label.

Executor recovery tests cover transient SQLite locks, explicit one-shot failure, unexpected database errors, owned interrupted work, and foreign lease isolation. Capability tests verify that the live device profile does not authorize another IP, protocol/port, VDOM, version, FQDN/wildcard type or deletion. Live evidence on 2026-10-23 comes from one already-approved request: TEST and TEST_Group on FortiOS v7.0.13 build 566, confirmed by readback, plus same-value IPv4/group PUT checks. No unrelated resources were modified.

Latest complete run: 137 passed in 182.94 seconds, with no skips and HTTP simulation enabled. Includes the regression preventing connection settings from changing after client creation and inheriting another endpoint's validation.

User management and usage update: 150 passed in 213.86 seconds with HTTP simulation enabled. Regressions cover exact grant preservation, inactive-account history and visibility, self-protection, CSRF, current local/firewall intersection, foreign-scope exclusion, repeated scan replacement, incomplete results, and migration retention. The HTTP integration scans twice through the production FortinetClient and verifies one saved result with two audit events. Desktop and 390px mobile UI checks used an isolated synthetic database.


Group authorization/cancellation update: 167 passed in 231.84 seconds with HTTP simulation and no skips. Coverage includes mandatory firewall groups, empty initial groups, exact-group permissions during submission/approval/execution, overlap isolation, revocation, hidden group names, approved-but-unstarted cancellation, terminal destination statuses and destructive-permission migration. Historical direct-request execution tests seed historical records; new direct submissions are rejected. Isolated desktop/mobile review confirmed the group forms and cancellation display.


Superadministrator request authorization: full HTTP simulation suite 171 passed in 237.24 seconds. Final focused run 15 passed in 27.85 seconds after visibility/copy adjustments. Coverage includes submission/approval without grants, self-approval denial, database-rechecked demotion/deactivation, disabled groups, reverse-join isolation, and explicit administer permission with automatic view access.


Superadministrator self-approval: 178 passed in 255.93 seconds with HTTP simulation and no skips. Includes own-request approval UI/endpoint, audit marker, role demotion with surviving grants, ordinary-user denial, schema constraints, historical execution and successful self-approved installation over real local HTTP. Four final endpoint/rendering checks also passed in 8.81 seconds.


Transfer selection update: 65 relevant form, view, user/access, catalog/import and connection regressions passed in 106.35 seconds. New tests cover all model multiple-choice widgets, escaped labels, bound selections, server preview and required/edit-initial values. Browser checks on isolated data exercised Add, Remove, Add all, Remove all, case-insensitive filters, filtered bulk moves, keyboard Space, isolation between fields, preview round trips, saved initial selection and visible required-field validation. Desktop/mobile layout inspection found no page-width overflow. JavaScript syntax, CSS build, Django checks and migration consistency pass.


## Firewall-group usage - 2026-10-23

Usage scans target an authorized firewall group and assess both address objects and address groups using policy and nested-group references. Results retain only matching local resource names and types. Each member replaces its latest saved observation; a failed member is marked incomplete and other destinations continue. View results requires no scan. Nullable group findings distinguish historical scans from assessed empty results.

Tests first reproduced missing group scan support and a cross-type intersection error. Full suite with local Postman HTTP simulation: 193 passed in 277.25 seconds, no skips. Coverage includes exact-group permission and membership rechecks, partial device failure, repeated replacement, old results, typed local filtering, and production-client HTTP scans with no writes. Read-only review found no actionable regressions. Desktop/mobile browser inspection used synthetic data and confirmed separate tables, group selection, saved-result navigation and no horizontal overflow.


Usage/VDOM update: full suite with Postman HTTP simulation passed 197 tests in 276.29 seconds. Added regression for all-to-all policies over HTTP, wildcard and negated reference classification, VDOM retirement/restoration, retained scans, group reassignment, permission and CSRF protection. Final focused verification covers the transactional row-lock refinement and rejection of removed or foreign explicitly supplied VDOMs. Desktop/mobile inspection used isolated synthetic data. Read-only live refresh produced complete potentially-unused results for the local object and group; no device mutations were performed.

Final focused run after destination locking/validation and responsive layout changes: 32 passed in 49.10 seconds.

Raw-list import final verification: 39 catalog/import/view/widget tests passed in 92.75 seconds. Includes the seven supplied examples, IP host normalization, wildcard classification, invalid inputs, duplicate/long generated names, prefix validation, TXT/BOM upload, 1,000-entry limits, CSV compatibility and atomic confirmation. Django checks, migration consistency and whitespace checks pass; local health returns HTTP 200.


HUB1 FQDN validation: 46 schema/capability/change/executor/HTTP integration tests passed in 67.13 seconds, including an approved three-type installation using the real device capability check and HTTP simulator transport. Final capability tests: 13 passed in 0.31 seconds. Live temporary resources separately verified FQDN/wildcard/subnet POST/PUT/readback, exact * and / names, group membership and complete cleanup; no approved installation was replayed. Other scopes, versions and deletion remain blocked.

## Combined production runtime validation (2026-10-24)

`tests/test_container_runtime.py` exercises unexpected child exits (including success exits), sibling termination, launch errors, preparation failure, and normal termination signals. The Docker image was built successfully. An isolated container with an empty database, synthetic secrets, and no network access applied migrations, collected 138 static files, started Gunicorn and one runner as UID 10001, returned HTTP 200 from `/health/`, and exited 0 on Docker stop. Compose configuration and unprivileged Nginx configuration with a temporary self-signed certificate passed validation. No real firewall execution or production deployment was performed; target-host TLS, permissions, and identity-provider behavior still require acceptance checks.

## Dependency upgrade validation (2026-10-24)

The production image was rebuilt with Python 3.14.9, Django 6.1.2, Pillow 13.0.0, cryptography 50.0.2, mozilla-django-oidc 5.0.2, and Gunicorn 26.2.0. The frontend builder uses Node 26.12.1 / npm 12.2.1 and Tailwind 4.3.3; HTTPX 0.28.1 and HTMX 2.0.11 were already current. Production transitive dependencies are pinned in `requirements.lock`. An isolated network-disabled runtime migrated an empty database, collected static files, started both processes as UID 10001, returned HTTP 200 on health, and stopped with exit code 0. Nginx stable was refreshed and reports 1.30.6. Frontend audit reports zero known vulnerabilities; `pip check`, Django system checks, migration drift checks, and the asset build pass. This does not replace a real identity-provider acceptance test.

Python 3.15.0 was evaluated separately: 258 tests passed and 21 integration tests were skipped. Production stays on 3.14 because the currently published Django 6.1.2 precedes documented official Python 3.15 support in 6.1.3.

The supported Python 3.14.9 environment also passed the complete suite: **258 passed, 21 skipped**. The skipped tests require integration services not exercised by this local upgrade validation. The project `.venv` now uses the user-local Python 3.14.9 installation; the former environment is retained at `.cache/venv-before-runtime-upgrade`. System-wide Node/npm were not replaced; production builds use the versions pinned in Docker.
