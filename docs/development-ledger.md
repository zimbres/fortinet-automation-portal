# Execution ledger

Plan: docs/superpowers/plans/2026-10-22-fortinet-portal.md

Approved: specification and direct execution, 2026-10-22.

Ruling: initialize a new develop branch in place — the project has no existing Git history or competing implementation — no existing branch needs isolation.
Ruling: use bundled Python 3.12 instead of the default Python 3.15 — Django 5.2 compatibility — runtime selection must be documented.
Ruling: use uv with a project-local cache because bundled venv ensurepip failed — dependencies stay isolated in .venv.
Discovery: Orbit DNS lookup failed; use official Fortinet documentation and preserve unsupported capabilities as blocked.

Preflight interfaces: accounts.User -> all foreign keys; scoped grants -> firewalls.VDOM uses lazy relation; adapter -> executor uses normalized records; approval -> executor requires immutable payload and digest; executor -> UI exposes sanitized step states; inventory -> adapter requires explicit completeness. No conflicting signatures found.

Task 1: started, incomplete. Added project packaging, development/production settings, custom user model, restricted user administration, append-only audit service, login/logout event handlers, and foundation tests.

Verification: Python 3.12 compileall passed for apps, config, manage.py, and tests. This proves syntax only. Django checks cannot run (ModuleNotFoundError: django); pytest cannot run (No module named pytest). No RED/GREEN claim is made: the initial test command was blocked by a missing test runner, not by an observed behavioral failure.

Blocker: uv dependency installation failed first with DNS/network errors and again after an authorized escalation with socket access error 10013. No automatic approval rejection was returned. The environment has neither Django, HTTPX, pytest, nor mozilla-django-oidc installed. Do not proceed to dependent tasks or claim Task 1 completion until dependencies can be installed and the specified tests run.

Ruling: prepare foundation source and setup documentation while dependency installation is blocked — these files can be reviewed and syntax-checked locally, but are explicitly unverified — cost if wrong: corrections after the first executable test run. Migrations remain ungenerated to avoid representing handwritten untested schema as verified output.

Tasks 2–10: pending; no firewall actions implemented or executed.

Startup follow-up: dependency installation succeeded on retry with authorized network access. Installed Django 5.2.18 and pytest 9.1.1; generated accounts/audit initial migrations and applied all migrations successfully. Django check reports no issues; the existing two foundation tests pass. Started the development server on 127.0.0.1:8000 and verified HTTP 200 at /admin/login/. No active superadministrator exists. These checks clear the installation blocker but do not establish full Task 1 acceptance or MVP completion.

## Continued implementation

The user confirmed removal of the blocker and requested continued implementation. Existing administrator identity and local data were preserved. A development key file was generated under ignored `.cache/` without printing key material.

Ruling: Tasks 2 and 3 share a schema dependency (ScopeGrant references VDOM); implement their first access/encryption tests together and generate Django migrations in dependency order. Test module names are grouped by behavior rather than copying every proposed filename.

Ruling: retain a coherent single integration commit for the tightly coupled initial apps instead of incomplete cross-app snapshots. All behavioral test results and deviations are recorded here.

Task 1: foundation verified through fresh pytest database migrations, Django checks, and clean-container migration. The initial audit and identity tests pass. No claim is made that blocked setup constituted a behavioral RED test.
Tasks 2–3: scoped capabilities, inactive-user checks, provisioned OIDC identity mapping, independent role presets, encrypted tokens, key ring rotation, firewall/VDOM registration, and write-only credential forms implemented. Initial four tests were observed failing before implementation and then passed. Additional OIDC issuer/audience/expiry tests failed before the validator was added. User/account and scope maintenance is available through restricted Django administration.
Task 4: adapter validation and sanitized HTTP handling implemented; 12 adapter tests initially failed with missing functionality, then passed. Production capability profiles remain empty; deletion reference completeness deliberately remains false. These are compatibility gates, not validated FortiOS support.
Tasks 5–6: immutable payload/digest, independent approval, idempotency, atomic transitions, single executor lease, permission rechecks, partial step history, and read-only reconciliation implemented. Five lifecycle tests initially failed, then passed. Added lease recovery, revoked permissions, and malformed post-write response tests. Malformed response regression was observed FAILED before the fix and RECONCILIATION_REQUIRED after it.
Task 7: transitive usage classification with cycle detection and unknown states implemented; both initial tests failed before implementation and passed afterward. Scan coverage is explicitly limited to IPv4 policies/groups. Revision metadata remains a follow-up limitation.
Task 8: full English portal routes and responsive Tailwind interface implemented. Missing-root/auth/CSRF tests failed before UI implementation. Fixed a reproduced missing-FQDN template failure. Desktop dashboard and mobile dashboard/request form were inspected; no second polish loop was performed. HTMX supports history filtering. Impeccable engine unavailable; design tokens and surface brief authored directly, with no claim of launcher validation or independent visual verdict.
Task 9: local Postman CLI 1.75.0 simulation runs the real executor and HTTPX client against stateful HTTP responses. Seven scenarios cover success, rejection, uncertain write, post-write read failure, partial completion, external group conflict, and unauthorized group. Simulator request events were inspected. The two added failure scenarios were observed failing and then passing after fixes. No device credentials or live mutations were used.
Task 10: Compose configuration, multi-stage image, non-root runtime, health check, backup/restore command and rehearsal, external keys, rotation command, and English operating documentation implemented. Production missing-secret checks and isolated SQLite restore tests pass. Docker image build succeeded; clean-container production check, migrations, collectstatic, and one-shot executor succeeded. The sole deployment-check warning is intentional HSTS preload omission (W021). Full Nginx TLS/target-host deployment remains unverified.

Review: fresh reviewer identified five correctness issues: post-write verification uncertainty, full group preservation during reconciliation, missing SSO entry point, prevalidation before create-and-add, and provenance restoration after reconciled creation. All five were addressed. Follow-up review found malformed post-write group parsing outside the uncertainty boundary; a failing regression test reproduced it, the fix passed. Remaining limitations are documented rather than presented as complete version support.

Dependency audit: npm audit initially reported four high-severity build dependency advisories. Tailwind CLI was pinned to 4.3.0 and compatible transitive updates applied; the resulting npm audit reported zero vulnerabilities. CSS build passed.

Verification checkpoint before final documentation: 61 tests passed including seven HTTP simulation scenarios. A subsequent malformed-readback regression adds one test; final totals are recorded in the completion entry below. No push, merge, publication, production deployment, or real firewall write was performed.

Final verification: 63 passed in 60.60 seconds with FORTINET_SIMULATION_URL set; no skipped tests in that run. Django system checks report no issues; makemigrations reports no changes; health returns HTTP 200 with status ok. Final CSS and Docker image builds succeeded. Compose configuration validates. The updated web server and single local executor remain running; the temporary simulation server is stopped after verification. Keep the new repository on develop: there is no remote or separate base branch to merge into.

Known follow-ups: supply exact FortiOS versions and version-specific mutation/reference contracts before enabling device writes; validate the target OIDC provider and complete HTTPS proxy deployment; retain scan revision metadata and a protected external audit sink where required. This delivery does not claim those environment-dependent validations are complete.

## Local catalog and installation update — 2026-10-23

Spec: `docs/superpowers/specs/2026-10-23-local-catalog-installation-design.md`.
Plan: `docs/superpowers/plans/2026-10-23-local-catalog-installation.md`.
User approved the written spec, the plan, native execution, and use of the current directory.

Tasks 1–3: local catalog with a shared database-enforced name namespace and independent catalog grants; transactional optimistic edits; CSV preview/confirmation with 1,000-row/1-MiB limits; firewall groups with explicit VDOMs and all-member authorization. Missing-feature tests were observed before implementation; task checks passed (15 catalog/access, 16 catalog/import, 4 initial firewall-group tests).

Tasks 4–6: separate immutable InstallationRequest/Target/Step and InstalledResource models preserve legacy requests and digests. Added all-target approval, target-level verified installation, shared executor scheduling/lease, and read-only reconciliation. Initial installation/execution/recovery tests failed for missing functionality, then passed (10 lifecycle, 24 adapter/executor, 11 recovery checks respectively).

Task 7: local catalog CRUD, CSV preview/confirmation, firewall-group management, installation preview/detail/decisions, separate device inventory, history/approval integration and catalog grant provisioning. Initial route/behavior tests failed before implementation; 24 view tests passed. Browser inspection used an isolated SQLite database on port 8001 with synthetic local fixtures, without adding test data to the user's database. Desktop catalog/import and mobile installation preview were inspected. One correction pass added form spacing and wrapping action buttons; confirmation showed no document overflow. Impeccable engine loading failed; existing PRODUCT.md and DESIGN.md supplied the visual direction.

Task 8: added seven real-HTTP multi-destination scenarios to the existing Postman simulation, with isolated mock state per destination. All seven passed, including matching/unowned objects, missing groups, partial failure and uncertain responses. Populated legacy schema migration test passed, preserving users, scope grants, encrypted credentials, request digests, provenance and audit while leaving the catalog empty. The local database was backed up to ignored `.cache/before-local-catalog.sqlite3` and all additive migrations applied successfully. Local health endpoints on ports 8000/8001 returned HTTP 200.

First complete suite: 112 passed, 3 failed. All failures were dashboard rendering errors from a Windows-encoded delimiter introduced during a template edit. Scanning apps/templates/docs found only that file invalid as UTF-8; corrected it and reran all three failing tests successfully.

Independent whole-change review identified five Important issues, all reproduced with isolated data: cached disabled destination state, missed opposite-resource namespace conflicts, stale no-op address verification, duplicate provenance after group recreation, and submit/approve visibility without view grants. Added regression tests, observed four executor failures and two visibility failures, then corrected them; 26 relevant lifecycle/permission/execution tests passed. An additional provenance reconciliation regression failed with revision 99 instead of 1 and was corrected by upserting the verified target/revision. A full first-target-success/crash/reconcile/untouched-target continuation test passed without replaying successful steps. No minor findings were deferred.

Ruling: keep the current develop checkout — the user explicitly selected in-place execution and there is no remote or second branch — cost if wrong: later branch separation is still possible from these commits.
Ruling: maintain task tracking manually when the packaged helper scripts were unavailable; subsequently discovered skills moved from version 6.4.2 to 7.0.1 — cost if wrong: less automated bookkeeping, mitigated by this ledger and commit history.
Ruling: retain the established interface using direct context when Impeccable's engine could not load — cost if wrong: no generated design-engine assessment; browser inspection and existing tokens cover the shipped surfaces.
Ruling: action capabilities intersect destination view grants — independent grants must not reveal hidden labels or snapshots — cost if wrong: administrators must explicitly grant view alongside submit/approve.
Final review boundary: live FortiOS compatibility and production enablement remain blocked by empty validated capability profiles; no live writes were authorized or performed. Further visual polish was set aside after the bounded inspection/correction pass. PostgreSQL semantics are outside this SQLite-only architecture. Cross-firewall rollback is intentionally excluded by the approved spec; partial outcomes remain visible rather than rolled back. The identified recovery-test gap was closed with the full continuation test.

Final verification: 123 tests passed in 160.57 seconds with FORTINET_SIMULATION_URL configured; no skipped tests. This includes the six review regressions, provenance reconciliation, full recovery continuation, populated legacy migration, and fourteen old/new HTTP scenarios. Postman request events were inspected and per-device state assertions establish distinct destination execution. Django checks report no issues; makemigrations --check --dry-run reports no changes; CSS build and diff whitespace checks pass. The existing localhost:8000 service and its active executor lease were preserved; restart that executor process to load the new scheduler when enabling the new workflow. The temporary visual server and simulator are stopped after verification. Production FortiOS write profiles remain empty. No push, merge, publication, or live firewall mutation occurred.

## Firewall connection configuration — 2026-10-23

User requested HTTP/HTTPS selection, accepting self-signed HTTPS certificates by ignoring certificate validation errors, removing Login, renaming Token to API Token, and removing Allowed groups. Clarification: retain the namespace restriction and label it Object name prefix. These direct requirements supersede the earlier HTTPS-only/certificate-verification/group-allowlist rules for firewall API connections. Portal-facing HTTPS/OIDC settings are unchanged.

Added persisted protocol with HTTPS as the migration default for existing devices. New registrations with a blank port use HTTP 80 or HTTPS 443; explicit/custom ports and existing encrypted tokens survive edits. Removed Login and Allowed groups from forms/models and the group allowlist checks from both executor paths. Retained object-prefix, ownership, approval, scope and version-capability checks. Updated field labels/help text, listed endpoints, and current documentation.

Observed six missing-feature failures before implementation: form labels/registration/editing, HTTP, self-signed HTTPS, and allowlist-free group installation. After implementation, 26 targeted configuration/execution/access tests passed. HTTP and HTTPS tests use the production client against real local servers; the TLS test generates its own self-signed certificate. Independent read-only review found no Important or Critical issues.

Before migration, verified zero RUNNING execution targets and identified the exact workspace executor command. Stopped only that executor process tree, created ignored backup `.cache/before-firewall-connection-config.sqlite3`, applied the additive protocol/removal migration successfully, released the stopped idle lease, and restarted the updated executor with a hidden window. The new executor lease is active and its error log is empty. No actual device calls were part of this verification.

Final verification: 129 tests passed in 165.99 seconds with all local HTTP simulation scenarios enabled and no skips. Django checks, migration consistency, and whitespace checks pass. The local web server was no longer running; confirmed no runserver process remained, then started the updated portal on 127.0.0.1:8000 with a hidden window and confirmed HTTP 200 at /health/. The temporary simulator was stopped after verification. Existing remote-device write capability profiles remain disabled.

## Executor lock recovery and authorized live validation — 2026-10-23

User reported an approved installation stuck in PENDING and explicitly authorized testing on HTTP 192.168.100.38 with its API credential. Used the existing encrypted credential; no plaintext key was added to source, output, or logs. Read-only inspection established FortiOS v7.0.13 build 566, root VDOM. The executor's error log showed an unhandled SQLite `database is locked` error in lease acquisition; its lease had expired and the process had stopped.

Tests reproduced the command exiting on temporary locks. The long-running command now retries known SQLite lock errors after three seconds, but does not suppress other database errors. On recovered database access, an owner with an active lease marks its interrupted RUNNING work for read-only reconciliation before processing further PENDING work. It never replays possibly sent writes or changes another worker's jobs. `--once` reports the temporary lock explicitly. Five recovery tests and related suites passed.

The pending approved request was `c315b482-acb7-457b-b95b-524ab01db0d5`, containing only IPv4 object TEST and address group TEST_Group. The configured prefix was the literal `all`, which did not match TEST. The user explicitly chose no prefix requirement for this firewall. Blank prefixes now permit arbitrary otherwise-valid names; nonblank prefixes retain their existing restrictions. Updated this device's prefix to blank with an audit event, updated form help, and applied the help-text migration.

Live validation was bounded to the exact already-approved object/group and destination, using a guarded client and a process-local capability exception. Both resources were absent beforehand. The real executor installed them and verified readback, recording SUCCEEDED and normal per-target steps/provenance. The separate validation assertion initially compared entire member dictionaries and encountered FortiGate's extra member metadata; the installation itself had already succeeded. Name-based membership verification then confirmed TEST in TEST_Group. Same-value IPv4 PUT and full-membership-preserving group PUT were verified by readback. No resources were deleted or unrelated configuration modified.

Automatic approval review rejected a proposed version-wide profile because one device's validation must not authorize every v7.0.13 firewall. Replaced it with the accepted narrower profile keyed to the exact version, HTTP address/port and root VDOM. Only install_address_subnet, create_group and install_group_members are allowed on that scope. Global profiles remain empty; different devices, protocols/ports, VDOMs, versions, FQDN/wildcard FQDN, legacy mutation operations and deletion remain blocked. Tests cover these exclusions.

Independent read-only review identified a connection-identity race: refreshed destination settings could authorize the new endpoint while an already-created HTTP client still used the old one. Reproduced the unwanted writes with a failing regression test, then bound execution to its initial protocol/host/port, VDOM/firewall identities and encrypted credential. Configuration changes before mutation now fail rather than borrowing another endpoint's validation. Six focused command/race tests passed after the fix.

The pre-review full suite passed 136 tests. The final whole-suite run passed 137 tests in 182.94 seconds, with no skips and local HTTP simulation enabled, including the added connection-race regression. Django checks and migration consistency pass; whitespace checks pass. Restarted only the verified local web server and the stopped executor, releasing only the completed validation lease with no RUNNING targets. Both helpers use hidden windows. The executor retained an active lease through the full regression run, its error log is empty, portal health returns HTTP 200, and the live approved request and its target both remain SUCCEEDED. The temporary simulator was stopped after verification. No broad version-wide profile, unrelated remote mutations, push, merge or publication occurred.
# User management and current local usage — 2026-10-23

User confirmed that Delete should deactivate accounts and preserve history, and that usage scans should replace earlier results while retaining audit events. Implemented superadministrator Edit/Delete actions, active-list filtering and reactivation, exact per-capability grant editing, optional password replacement, transactional validation, CSRF and self/last-administrator protections.

Usage classification still reads the complete firewall policy/group graph, then shows the intersection with local address names. Both catalog-view and scoped VDOM-view permissions are enforced, including independently within the latest-results service. Rescans update one row per VDOM; incomplete scans replace stale results. Migration retains the latest historical row before adding database uniqueness. Each scan remains audited.

Failing regressions preceded implementation, including migration duplicates and foreign-scope leakage. Final suite: 150 passed in 213.86 seconds with local Postman HTTP simulation enabled. Production-client integration verifies two scans, one result and two audit events. Django checks, migration consistency, CSS build and whitespace checks passed. Independent read-only review reported no Important/Critical findings. Desktop and 390px mobile checks used an isolated synthetic database; no real accounts or firewall configuration were modified by those checks.

Created a consistent local SQLite backup at .cache/before-user-usage-changes.sqlite3, applied inventory migration 0004 successfully, and started the updated local portal on port 8000. Temporary simulator and isolated visual server were stopped. Existing executor was left running.



## Group permissions and cancellation � 2026-10-23

User requires mandatory firewall group membership, group-granted permissions and group-name request targets. User explicitly permits removing previous permissions and incompatible database data. Ruling: preserve catalog/history, discard individual VDOM grants, initialize group access for active superadministrators, and cancel untouched historical direct-target requests � avoids broadening existing nonadministrator access or executing incompatible pending intent.

Replaced ScopeGrant with GroupGrant. User provision/edit/admin and access displays use named groups. Firewall forms require groups; group edits cannot orphan a device. Empty groups support first-device registration. Requests freeze group identity/name and destinations; group-specific grants and current membership are checked during approval/execution, while added members never expand submitted targets. Generic device visibility derives from group membership. Direct legacy submission is disabled.

Cancellation updates approval, execution and pending targets in one transaction, conditional on execution remaining unstarted. Approved requests waiting for the executor can also be cancelled. Migration repairs earlier cancelled/pending status mismatches. Running/completed results are preserved.

Observed failing tests covered missing grants, direct submission, cancellation statuses and overlapping-group approval authorization. Independent read-only review found approval could borrow the requester's submit permission from an overlapping group; reproduced then fixed with exact-group checks. A separate regression reproduced hidden group names appearing on the firewall list, then passed after filtering memberships by authorized groups. Existing historical executor tests now seed historical requests directly because creating direct-target requests is intentionally unsupported.

Desktop and 390px mobile inspection of isolated synthetic data confirmed group-only request selection, group permission fields, mandatory firewall group selection and CANCELLED approval/execution/target states. No real account or firewall writes were used for UI tests.


Final verification: 167 passed in 231.84 seconds with Postman HTTP simulation enabled and no skips. Django checks, migration consistency, CSS build and staged whitespace checks passed. The preceding run exposed six legacy tests still calling the intentionally disabled submission service; converted those fixtures to historical seeding and all 24 focused recovery/authorization/migration tests passed before the final full run.

Created consistent backup .cache/before-group-permissions.sqlite3, stopped only verified local web/worker processes, and successfully applied accounts 0004 and changes 0003. Actual database has zero ungrouped firewalls. Automatic approval review initially rejected restarting the executor because pending approved work had not been ruled out. Read-only inspection confirmed zero approved pending/running requests and zero running targets; the safer restart rechecked those conditions and was accepted. Portal health returns HTTP 200 and exactly one executor lease is active. No real firewall mutations were needed. Other users must receive new group grants through Users & access.


## Superadministrator requests and approvals � 2026-10-23

User requests that superadministrators can submit and approve requests. Active superadministrators now automatically receive view/submit/approve access to enabled groups without explicit GroupGrant rows. Independent approval still blocks self-approval; administer remains explicit. Both capability checks and visibility queries reread the stored identity so demotion or deactivation takes effect despite stale session objects. Disabled groups/scopes stay unavailable. User access screens explain automatic permissions.

Initial feature tests failed without explicit grants, then 34 focused tests passed. Added regressions caught chained-query borrowing of a disabled group's grant and a view/administer visibility inconsistency; both were corrected. Final full HTTP-simulation suite passed 171 tests in 237.24 seconds. After the final visibility/copy adjustments, all 15 focused superadministrator, user-management and installation-view tests passed in 27.85 seconds; another 28 user/view tests also passed. Django checks, migration consistency and whitespace checks pass. Fresh read-only review reported no actionable findings. No schema migration was needed.

Verified zero approved pending/running work before restarting the existing idle local web/executor helpers; released only the stopped worker's lease. Health remains HTTP 200 and no real firewall changes were performed. Final visibility helper changes required only a web reload, as executor authorization checks were unchanged.


## Superadministrator self-approval - 2026-10-23

User explicitly authorizes superadministrators to approve their own requests. Ordinary users still require a different authorized approver. Added a persisted self_approved marker to installation and historical requests; database constraints permit matching requester/approver only with the marker and require the marker to describe matching identities. Approval services set it only for a current active superadministrator approving their own request. Shared execution authorization rechecks active superadministrator status before device writes, so demotion revokes the exception even when explicit group grants remain. Approval audit events include the marker.

Approval queues include a superadministrator's own pending requests. Own-request approval controls are visible; self-rejection remains unavailable. Details identify the self-approved superadministrator. Updated form/help/operational copy to reflect the exception.

Initial tests reproduced the blocked self-approval. All 26 focused tests passed; four additional endpoint/rendering checks passed in 8.81 seconds. Full suite with local Postman HTTP simulation: 178 passed in 255.93 seconds, no skips. The new HTTP test executes a self-approved installation successfully through the production HTTP client against the simulator. Fresh read-only review reported no actionable findings. Desktop/mobile inspection used an isolated database and confirmed the own-request approval control; no real request was approved for visual testing.

Created consistent backup .cache/before-superadmin-self-approval.sqlite3. Verified no approved pending/running work, stopped only verified local web/executor helpers, applied changes migration 0004 and released only the stopped idle worker's lease. Restarted helpers with the same empty-queue guard. Health returns HTTP 200, the executor error log is empty and exactly one executor lease is active. No real firewall changes were performed.


## Dual-box transfer selection - 2026-10-23

User requests replacing multiple selection lists with boxes and left/right arrows, Add and Add all. Implemented one reusable TransferSelectMultiple widget across catalog group members, installation objects/groups, firewall memberships, firewall-group destinations and user group permissions. Fixed role choices remain checkboxes and single destinations remain dropdowns. Added search, counts, checkbox selection without Ctrl, filtered bulk moves and remove counterparts. Native selects remain canonical submitted values and work without JavaScript. Enhancement synchronizes option.selected, handles reset/external change, prevents search Enter from submitting, labels controls and announces transfers. Required fields use visible-control validation.

Initial widget tests failed before implementation. Widget template lookup failed until investigation established that apps.portal was not registered as a Django app; added its model-free AppConfig so the standard form renderer discovers its app template. Replaced installation form.as_p with a shared field include to avoid nesting the block widget inside paragraph markup. No schema migration was required.

65 relevant regressions passed in 106.35 seconds. Node syntax check, CSS build, Django checks, migration consistency and whitespace checks pass. Fresh read-only review reported no actionable findings. Real browser checks on isolated synthetic data verified individual/all/filtered moves, keyboard selection, independent field state, preview persistence, existing selections and required validation. Desktop and mobile inspection found no horizontal page overflow. Reloaded only the verified local web server; executor authorization and lifecycle were unchanged. No real permissions or firewall configuration were changed by testing.


## Highlighted transfer lists - 2026-10-23

User clarified the desired control with a screenshot: native left/right selection boxes, highlighted rows, arrows to move highlighted items or all. Replaced checkbox rows with native unnamed multiple-select list boxes. Highlight is transient and separate from canonical source option.selected; only transfer actions change submitted values. Search clears highlights in its own pane, and bulk actions continue to respect filters. Fourteen relevant tests passed in 20.59 seconds. Browser checks confirmed highlighting alone does not select a submitted value, add/remove highlighted items, move all in both directions, filtered bulk moves, server preview preservation and mobile layout without horizontal overflow. Node syntax, CSS build and Django checks passed. No schema or executor changes were needed.


## Firewall-group usage - 2026-10-23

Usage scans target an authorized firewall group and assess both address objects and address groups using policy and nested-group references. Results retain only matching local resource names and types. Each member replaces its latest saved observation; a failed member is marked incomplete and other destinations continue. View results requires no scan. Nullable group findings distinguish historical scans from assessed empty results.

Tests first reproduced missing group scan support and a cross-type intersection error. Full suite with local Postman HTTP simulation: 193 passed in 277.25 seconds, no skips. Coverage includes exact-group permission and membership rechecks, partial device failure, repeated replacement, old results, typed local filtering, and production-client HTTP scans with no writes. Read-only review found no actionable regressions. Desktop/mobile browser inspection used synthetic data and confirmed separate tables, group selection, saved-result navigation and no horizontal overflow.

Created .cache/before-group-usage.sqlite3 before applying inventory migration 0005. Reloaded only the verified local web helper; the executor was left running. No real firewall calls were made for this change.


## Usage assessment and VDOM removal - 2026-10-23

User reported Unknown assessments and requested VDOM deletion with improved firewall action formatting. Added regressions reproducing all/negated policy references making all unreferenced resources unknown. Classification now distinguishes named references from traffic matching. Local HTTP simulation includes all-to-all policies. Read-only live inventory and a fresh saved scan on the authorized test firewall produced one local address and one local address group as potentially_unused, with complete inventory. No device writes were performed.

VDOM removal retires and disables the registration, preserves history, and is reversible by adding the same name. Superadministrator confirmation and CSRF are required; group destinations must first be reassigned. Fixed reassignment of an existing firewall member to another VDOM. Reviewer identified validation outside the transaction as a concurrency risk; moved validation and VDOM row locks inside the group transaction. Firewalls now use responsive records with explicit firewall actions, endpoint/group/version details and a separate row of actions per VDOM. Isolated desktop/mobile inspection confirmed the layout and blocked/removable confirmation states. Created a consistent backup before firewalls migration 0005.


Full HTTP simulation suite: 197 passed in 276.29 seconds. Subsequent review applied the same VDOM row-lock/validation guard to set_firewall_groups, including explicitly supplied VDOM ownership and active-state validation; its new regression failed before the fix. Rebuilt CSS, passed Django checks and migration consistency, and verified health HTTP 200 after reloading only the local web helper. Executor lifecycle was unchanged.

Final focused run: 32 passed in 49.10 seconds. No remaining review findings after applying destination locks in both group membership paths.

## Connection-check access fix - 2026-10-23

The firewall configuration showed Check connection to superadministrators, but its endpoint used the explicit administer group grant and returned 404 when the grant was absent. The endpoint now revalidates superadministrator status and permits active registered VDOMs directly; other users retain explicit scoped administer checks. Removed/disabled destinations redirect with a recovery message and no remote call. Regression tests reproduced both failures before the fix. All 13 connection/configuration/VDOM tests passed in 19.70 seconds; Django checks and whitespace validation pass. No grants or device configuration were changed.


## Raw address-list import - 2026-10-23

User requested pasting/uploading one value per line, automatic IPv4/subnet/FQDN/wildcard classification and an object-name prefix. Imports now auto-detect raw lists or the existing CSV header. Raw generated names use canonical values, wildcard_ and underscore subnet masks; long names retain their prefix and a stable hash suffix within 79 characters. Optional prefix also applies to CSV names. Existing server-owned preview, expiry, digest, actor binding, permission rechecks, transaction rollback, duplicate rejection and idempotent confirmation remain in use. Blank lines are ignored; invalid network addresses, IPv6, URL/port/path values and malformed domains are rejected. Limits remain 1,000 entries / 1 MiB.

Initial tests reproduced missing parser/prefix support. Review identified quoted-header compatibility and a whitespace-header KeyError; both were reproduced in regression tests and fixed using CSV field-based detection. Isolated browser preview of the user's seven sample values confirmed every inferred type and generated name on desktop and mobile without page-width overflow. No real catalog objects were created for visual inspection and no firewall calls were made. No schema migration was needed.

Raw-list import final verification: 39 catalog/import/view/widget tests passed in 92.75 seconds. Includes the seven supplied examples, IP host normalization, wildcard classification, invalid inputs, duplicate/long generated names, prefix validation, TXT/BOM upload, 1,000-entry limits, CSV compatibility and atomic confirmation. Django checks, migration consistency and whitespace checks pass; local health returns HTTP 200.


## Exact address import names - 2026-10-23

User clarified that imported names must equal the address or prefix plus address. Raw-list import now preserves the trimmed original address exactly in the name, including wildcard markers, subnet slash, explicit /32, letter case and trailing domain dot. Stored address values still undergo normal normalization. Removed automatic wildcard substitutions, slash substitutions and hashed truncation. Name validation now accepts * and /; the existing client already percent-encodes names in resource paths. Overlength names fail preview rather than being renamed. Existing catalog records are unchanged. Regression tests reproduced the prior substitutions before correction.
Verification: 47 import/catalog/view/Fortinet schema and encoded-name client tests passed in 58.44 seconds. Django checks, migration consistency and whitespace checks pass. Reloaded the verified local web server; health returns HTTP 200.


## HUB1 FQDN capability validation - 2026-10-23

Approved installation eda4b7fb-d0ec-4cae-a6b7-385cad09123b failed preflight with zero steps. Its nine addresses included three IPv4, three FQDN and three wildcard FQDN definitions. HUB1's exact device profile only covered IPv4/groups. Verified official Fortinet wildcard-FQDN documentation and simulator round trips, then used the previously authorized test device for isolated UUID-prefixed resources. Live POST/PUT/readback succeeded for all three address types, including exact wildcard and slash names. Group POST/PUT preserved all test members; removed only the test group/addresses and confirmed their absence. Evidence is in .cache/address-types-live-evidence.json and the audit event firewall.compatibility_validated.

Extended only the exact v7.0.13 / HTTP192.168.100.38:80 / root capability set for FQDN and wildcard FQDN. Global version profiles remain empty, deletion remains blocked and other devices/versions do not inherit this validation. Improved blocked-write errors to identify operation/version. The failed request and its immutable approval/history are preserved; it is not requeued. No real installation was replayed by this change.


Verification: 46 targeted and HTTP simulation tests passed in 67.13 seconds; final 13 capability/client tests passed in 0.31 seconds. Read-only review found no actionable findings. Django checks, migration consistency and whitespace validation pass. Created .cache/before-fqdn-profile.sqlite3, verified zero approved-pending/running work, stopped only the verified old executor, released only its exact lease and restarted the helper hidden. One new executor lease is active, its error log is empty and health is HTTP 200. The reported failed request remains FAILED.

Fortinet reference: https://docs.fortinet.com/document/fortigate/7.0.0/administration-guide/217973/using-wildcard-fqdn-addresses-in-firewall-policies
