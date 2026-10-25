# Operations

## Rapid indicator blocking workflow

The portal lets authorized people without direct firewall access add IP addresses and FQDNs to an existing address group already used by firewall rules. For example, a security team can submit malicious indicators quickly to a preconfigured block group without receiving firewall credentials. Each indicator is an address object; the address group collects those objects for the existing policy. Firewall administrators must configure and verify that policy first: adding group members does not create a deny rule or change policy order.

1. A firewall administrator prepares the policy and target address group and grants portal access to the appropriate firewall group. Confirm the device and operation have a validated write profile.
2. The security team creates IP/FQDN objects locally, or imports a CSV, selecting the existing address group. Catalog changes alone do not alter the firewall.
3. Submit an installation request for the target firewall group. An authorized approver reviews the immutable request; ordinary requesters cannot approve their own changes. Superadministrators may self-approve.
4. The runner rechecks permissions and observed configuration, executes the approved changes, and reads back the result. Watch approval and execution status in the portal. Investigate failures or reconciliation-required results before treating an indicator as blocked; do not blindly replay uncertain writes.

No firewall UI account or API token is given to the requesting user. Firewall credentials remain encrypted in the portal. Blocking effectiveness depends on the existing policy, its order, and FortiGate address/FQDN behavior.


## Catalog and installation workflow

See [local catalog operations](local-catalog.md) for catalog grants, bulk CSV creation, firewall groups, immutable installation requests and per-target read-only recovery. Legacy request instructions below apply only to legacy requests.

## Development

Use Python 3.12 or 3.13, install `.[test]` into `.venv`, and run `npm ci && npm run build`. Apply migrations before starting either process. Start the web application with `manage.py runserver 127.0.0.1:8000` and the executor in a second terminal with `manage.py run_executor`. The executor does not start inside web requests.

When `.cache/oidc-test.json` and `.cache/oidc-test-client-secret` are present, development settings load the saved OIDC configuration automatically, including with the normal `manage.py runserver 127.0.0.1:8000` command. Explicit environment settings take precedence; set `PORTAL_AUTH_MODE=local` to disable the saved OIDC configuration. These files remain ignored by Git, and production settings do not read them.

Create an administrator interactively using `manage.py createsuperuser`. There are no default credentials. Generate a development encryption key using `manage.py create_encryption_key`; development settings read `.cache/encryption.keys` when no explicit external key path is configured. This file is ignored by Git. Restrict its Windows ACL or Unix file permissions and back it up separately. Restart the application after changing key configuration.

Register a firewall with an API Token, HTTP/HTTPS protocol, port, and Object name prefix. HTTPS accepts self-signed certificates; no per-firewall address-group allowlist is required. Create a firewall group first, then select at least one enabled group during firewall registration. Register a second user with Approver access to the request group; ordinary submitters cannot approve their own requests; superadministrators may. Users & access maintains identity, role labels and explicit group grants. Registration and editing both use separate View, Submit, Approve and Administer firewall-group selectors. Select each grant explicitly; role labels do not populate group grants. Changing a label alone does not change grants. Existing superadministrator global capabilities still apply.

## Account identity and sign-in

Local sign-in uses the account email and password, with case-insensitive email matching. Registration and account editing use a single Email field. Nonempty emails are unique regardless of case; existing internal usernames remain stable for historical records.

OIDC links a pre-provisioned account by its verified email (`email_verified: true`). First sign-in binds the trusted issuer and subject; an existing different binding is rejected. Unknown emails do not create accounts. Names are synchronized from the provider at sign-in without changing roles or grants. Local password sign-in remains available when OIDC is enabled.

When a superadministrator edits an OIDC-linked account, Email and password are read-only; issuer and subject are not shown; role labels, active state, catalog access and explicit firewall-group grants remain editable. Identity fields are preserved by the update service even if a request attempts to change them.

OIDC-linked users see personal information as read-only and must manage their password through the identity provider. The server rejects profile or password updates from these accounts. Local users can edit names/email and change their password through My profile.

## Permission guidance

Permission-denied responses use the shared Access required page in development and production. It asks the user to contact a superadministrator for the relevant catalog, firewall-group or administrative access and provides Return to Overview. Internal exception details are not displayed, and the HTTP response remains 403.

Live searches, status polling and other HTMX updates display the same guidance in the main content area when a permission-denied response arrives, replacing stale controls and stopping timers in that area. CSRF failures and intentionally hidden 404 resources retain their separate handling.

## Live search

Address-object search matches either the object name or its normalized value, case-insensitively. Address-object and address-group catalogs and Operation history filter automatically after a 300 ms pause in typing. The query stays in the URL without creating a history entry for every keystroke. A new history filter starts at page one. Catalog bulk-selection controls reinitialize after each filter update, clearing selections from earlier results.

Device inventory filters the already-loaded names and values instantly in the browser. Loading a scope still requires Load inventory; typing does not issue firewall requests. Available/Selected transfer controls retain their existing immediate filters.

## Required local password changes

Registration links OIDC accounts by verified email and does not request an external issuer or subject. Issuer and subject are also omitted from user editing; existing OIDC bindings are preserved internally.

For local accounts, superadministrators can select Require password change at next login during registration or editing. A local password must exist or be supplied. Marked users are directed to `/password/change-required/`; existing authenticated sessions are also gated on their next request. Application pages and actions remain blocked until a valid, different password is submitted. Sign out remains available. Completion clears the requirement, preserves the current session and records a password-change audit event without credentials.

The requirement is disabled for OIDC-linked accounts, whose password policies remain at the identity provider. Existing accounts are unmarked by default.

## Inventory and usage pagination

Device inventory and each address-object/address-group usage table display 25 rows per page, with Previous, Next, numbered pages and a visible result range. Each usage table maintains its own page independently, including across firewall/VDOM sections.

Pagination uses the already-loaded inventory or saved scan results and does not make firewall requests or start scans. Inventory search matches the full loaded result set, resets to page one when changed, and retains the selected scope. Clearing the filter restores all loaded rows. Without JavaScript, the full table remains available.

## Profile pictures

The sidebar and My profile use Gravatar with a normalized SHA-256 email identifier by default. A failed or missing image falls back to the user's initial. Users can upload a PNG, JPEG or WebP picture up to 2 MB and 4096 pixels per side; uploads are re-encoded as 256-pixel PNGs with metadata removed. Uploaded pictures override Gravatar, and Use Gravatar removes the upload.

Pictures are stored under `data/media/avatars/` and served only to the signed-in owner through `/profile/picture/`, including in production. Preserve this directory with the application data. OIDC users can manage their picture while identity fields and passwords remain provider-managed.

## Live status updates

Overview, Operation history, Approvals, and active installation details refresh their status sections every five seconds. History retains the applied filter and page. Polling pauses in hidden tabs or while focus or selected text is inside the updating section. Expanded execution steps and horizontal table positions are preserved. Installation details stop polling after success, failure, partial success, cancellation, or rejection; requests requiring reconciliation continue updating.

These updates only read portal state. The separate executor must still be running to process approved requests.

## Execution

Active superadministrators can view, request and approve installations for any enabled firewall group without explicit group grants. They may approve their own requests. The self-approval is recorded and execution requires that they remain active superadministrators. Administer remains an explicit capability.

New requests target a named firewall group. Access is rechecked on that exact group during approval and immediately before writes. The upgrade removes old individual-device permissions; active superadministrators receive initial group access and must configure other users.

Cancelling a request before execution begins atomically cancels its execution and all pending destinations. This includes approved requests still waiting for the executor. A running or completed operation cannot be cancelled retroactively. Old cancelled/pending records are repaired during migration.

Users & access provides Edit and Delete actions for superadministrators. Edit maintains identity, optional password changes, role labels, catalog access and each explicit firewall-group capability separately. Delete deactivates the account and hides it from the active list while retaining request and audit history. Show inactive users to edit and reactivate an account. Self-deactivation, self-demotion and removal of the last active superadministrator are blocked.

Object usage retains one current scan per firewall/VDOM and displays only address objects present both on that firewall and in the local catalog. Repeated scans replace the result and retain their audit events. Catalog view and scoped VDOM view permissions are both required.

All mutation workflows require approval. Ordinary users require a different approver; active superadministrators may approve their own requests. Inventory, connection checks, and usage scans are read-only and require the corresponding scope capability. Approval binds an immutable payload. Rejected/cancelled requests cannot execute. The executor rechecks active identities and permissions immediately before writes.

Run exactly one executor. It uses a database lease and conditional claims. After an abnormal stop, wait for the five-minute lease to expire; abandoned RUNNING requests require reconciliation rather than automatic replay. Never manually reset them to PENDING. An active worker refreshes its lease before mutations; individual HTTP calls have bounded timeouts. Do not suspend/resume the executor process across ownership transfer; terminate an old process before starting a replacement. The Fortinet API does not provide a portal fencing token.

Version-wide write profiles remain empty. The exact HTTP 192.168.100.38:80/root/v7.0.13 device scope has live evidence for IPv4 address installation and group creation/member updates; other scopes/types remain blocked. Unknown-version requests fail before any remote write. Do not populate profiles based solely on simulation results. Authoritative reference inspection is not yet validated, so deletion is blocked even after a version profile is added.

Read-only reconciliation is available on uncertain request details for scoped administrators, or through `manage.py reconcile_requests REQUEST_UUID --actor USERNAME`. It never replays changes. Partial create-and-add workflows retain the created object and show successful steps. Investigate partial results before submitting another request.

## Credential rotation

Create a fresh Fernet key in a protected file. Configure the key ring with the new key first and the previous keys on subsequent lines. Restart all application processes, then run `manage.py rotate_credentials`. The command refuses concurrent overwrites and rolls back on decryption failure. Confirm application decryption and backup restoration before retiring old keys. Old encrypted backups still require their original keys.

## Audit and usage

Login attempts, logout, provisioning, access changes, firewall configuration, submissions, decisions, scan completion, and execution results are recorded. Recoverable secrets never belong in audit metadata or step snapshots. Audit records are append-only through application APIs; database administrators can still modify SQLite files. Use an external protected log destination where formal tamper resistance is required.

Usage scans cover IPv4 firewall policy source/destination address references and nested groups. Findings are potentially unused within that coverage, not proof of no CMDB references. Incomplete inventory and unsupported constructs produce unknown results. No scan deletes objects.

## Temporary database locks

The long-running executor retries SQLite database/table lock errors after three seconds instead of exiting. If a lock interrupted claimed work, its owner marks RUNNING requests/targets for read-only reconciliation once database access returns; it does not replay possible device writes. Unclaimed PENDING requests can continue normally. A different active executor still blocks startup. `--once` reports a temporary lock as a command error so its caller can retry. Other database errors are not suppressed.


## Multiple selection controls

Multiple-choice fields use Available and Selected list boxes with highlighted rows and transfer arrows. Click an item to highlight it, then use Add or Remove; Add all and Remove all transfer every visible matching item. When filtering, the buttons say Add all shown or Remove all shown. Each box has search and a count. Saved choices appear on the Selected side when editing. Changes are submitted only when the form is saved or previewed. On mobile the boxes stack vertically.

Usage scans now target a firewall group and report both address objects and address groups per member firewall / VDOM. View results reads saved observations without network access. Only resources also present locally with the same type are shown. Device failures remain visible as incomplete results while other members continue; rescanning replaces each previous result and retains audit events. Older results require a new scan to assess address groups.

## VDOM removal

Superadministrators can use Delete VDOM on the Firewalls screen. Confirmation removes the VDOM from active configuration and disables it while retaining its identifier, requests, scans and audit history. This is a local portal change; it does not delete a VDOM from the device. Existing firewall-group destinations must be reassigned before removal. Add the same name on the same firewall to restore the registration and its history. Group reassignment locks and validates destination VDOMs in the same transaction as membership updates.

Usage assessment tracks named configuration references, including nested groups. A policy referencing the built-in all address does not reference every other named object, and address negation still references the listed objects. Neither construct makes the remaining observations unknown. Missing or unresolved references and incomplete inventories remain conservative. Saved observations require a fresh scan after classifier changes.

## Device write validation

The device-scoped v7.0.13 profile for HUB1 (HTTP 192.168.100.38:80, root VDOM) includes IPv4, FQDN and wildcard FQDN installation plus group creation/member updates. On 2026-10-23, isolated temporary resources verified POST, same-value PUT, readback, exact wildcard/subnet names and group membership, followed by confirmed cleanup. No global version profile is enabled. Unsupported-device errors identify the operation and observed version. A terminal failed request remains part of history; submit and approve a new installation after fixing the cause. Failed targets are not reset or replayed automatically.

## Production process lifecycle

Production runs the web app and runner together as non-root processes in the `web` container. Use `docker compose logs -f web` for their combined stdout logs and `docker compose restart web` to restart both. Do not start another runner alongside this container. See [deployment](deployment.md) for secrets, volume permissions, shutdown, and migration from the former separate-executor layout.

When SSO verifies an identity but no active matching portal account is authorized, the login page shows: “Your SSO account does not have access to this portal. Contact your superadministrator to request access.” Missing, inactive, and incompatible identity bindings share this message. Failed or cancelled SSO authentication uses a generic retry message; local email/password failures remain generic.

Creating address groups requires an active Administrator role plus Catalog Manage access, or an active superadministrator. Catalog Manage alone does not permit creating groups. Operators with Catalog Manage can still create/import address objects and add them to existing groups. Existing group editing and membership permissions are unchanged.

Audit entries generated by execution display the actor as “Executor (background runner)” in the audit page and new stdout audit messages. This identifies the automated process, while the request retains the accountable requester and approver. Failed login attempts and credential rotation have separate descriptive labels. Historical audit-page labels are derived without modifying append-only records.
