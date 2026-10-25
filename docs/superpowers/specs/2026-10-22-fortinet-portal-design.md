# Fortinet Automation Portal — MVP Technical Specification

Status: approved by the user on 2026-10-22. Requirements come from PRODUCT.md; defaults identified below were accepted through specification approval.

## Outcome and scope

Build an internal English-language portal that lets authorized users request Fortinet address changes, obtain approval from a different authorized user, execute the approved workflow through the backend, and inspect verified outcomes and audit history.

The MVP includes firewall and VDOM registration, superadministrator-managed accounts, roles, address and group inventory, address creation and deletion, group membership changes, approval, execution, reconciliation, and unused-object alerts. Support IPv4 hosts/subnets, FQDNs, and wildcard FQDNs. Selecting an existing object or creating one before adding it to an existing group are explicit alternatives. Editing an address object follows the same approval boundary. No policy modification, automatic deletion of unused objects, or automatic group creation is included.

## Architecture

Use a modular Django 5.2 LTS monolith with server-rendered templates, HTMX, compiled Tailwind CSS, SQLite, HTTPX, and Python ipaddress. Modules: accounts, firewalls, fortinet, changes, and audit. Use `changes` as the Python package name to avoid confusion with request objects and third-party HTTP packages.

Views validate forms and call application services. Services enforce permissions and lifecycle rules independently of the UI. The Fortinet adapter owns HTTP, payload mapping, version capabilities, pagination, and sanitized errors. No browser receives firewall credentials or calls a firewall directly.

Docker Compose provides the Django application and HTTPS reverse proxy. A separate management-command execution process uses the same image and database without Redis or Celery. This simple single executor is the proposed initial way to keep network calls outside web requests and serialize portal writes. It is not a general distributed queue.

## Proposed access model

Use scoped capabilities: view inventory/history, submit changes, approve changes, and administer firewalls. Viewer, Operator, Approver, Administrator, and Superadministrator are proposed role presets. Operator and Approver capabilities may coexist, but the same identity may never approve its own request. Administrative status does not bypass this rule. Only Superadministrator manages users and role assignments. Default access is denied without explicit firewall/VDOM grants.

Provision accounts through the superadministrator. OIDC login must match a provisioned account; it must not silently create or elevate accounts. Bind external identities using issuer and subject rather than email alone. Local accounts support development and bootstrap, with Django password hashing. Production login mode is explicit; SAML terminates at an OIDC broker.

## Data model

- User: Django custom user, external issuer/subject binding, active status, and role assignments.
- Firewall: name, management address, HTTPS port, enabled state, encrypted API credential, optional API-account label, observed FortiOS version, and configured mutation namespace.
- VDOM: firewall, name, enabled state; unique per firewall.
- ScopeGrant: user or role group, VDOM, and granted capabilities.
- ChangeRequest: UUID, requester, firewall/VDOM, operation, immutable validated payload, payload digest, idempotency key, approval status, execution status, approver, timestamps, and sanitized outcome.
- ExecutionStep: request, step type, sanitized before/after state, result, and timing. This records partial completion of create-and-add workflows.
- AuditEvent: actor, event type, request reference, sanitized metadata, and timestamp; no application update/delete path.
- ObjectReference: VDOM, object name/type, portal ownership and originating request; this is provenance, not authoritative configuration.
- InventoryScan/UnusedObjectFinding: scope, scan completeness/time, observed revision, object identity, and usage assessment.

Store all times as timezone-aware timestamps. Enforce uniqueness and cross-model scope consistency in application services and applicable database constraints. Approval and execution transitions use atomic conditional updates rather than process-local locks.

## Approval and execution lifecycle

Approval states: PENDING, APPROVED, REJECTED, CANCELLED. Execution states: PENDING, RUNNING, SUCCEEDED, FAILED, RECONCILIATION_REQUIRED. Execution cannot start unless approval is APPROVED and the approver differs from the requester.

The proposed approval boundary covers every mutation workflow, including deletion and group membership changes. Authorized read-only inventory and connection checks do not require approval under this proposal. Approval covers an immutable payload and its digest; changing scope or payload requires a new approval. Rejected or cancelled requests never execute.

The executor atomically claims one approved request, rechecks active identities and scope permissions, reads current firewall state, validates prerequisites, performs the approved steps, then reads back the affected resources. Success requires the observed result to match the requested result. No database transaction remains open during network I/O.

Use one executor with a database-backed ownership lease and heartbeat; reject a second active executor. A RUNNING request abandoned by a crashed executor becomes RECONCILIATION_REQUIRED, never blindly replayed. An administrator can initiate read-only reconciliation; further mutations require a new approved request.

Timeouts or uncertain write outcomes require reconciliation. Proven rejection may become FAILED. If object creation succeeds but group addition fails, retain and report the created object and partial result; do not delete it automatically. Idempotency keys are bound to requester, scope, and payload digest; conflicting reuse is rejected.

## Fortinet adapter and compatibility

Use HTTPS with certificate verification, bounded timeouts, bearer API tokens, escaped resource names, explicit VDOM parameters, and redirects disabled. Load credentials only within the backend request boundary. Do not log Authorization headers or raw credential-bearing exceptions.

Candidate endpoints supplied in the architecture are `/api/v2/cmdb/firewall/address`, `/api/v2/cmdb/firewall/addrgrp`, and their named-resource variants. Policy and reference inspection endpoints and all version-dependent behavior must be checked against maintained Fortinet documentation before implementation. Record the resulting contract and reusable mocked scenarios locally.

Exact FortiOS versions are not yet known. Do not claim universal mixed-version support. Permit writes only for explicitly validated version/capability profiles; unsupported devices may be registered but execution is blocked with an actionable reason. Foundation development and simulated integration do not require live device credentials.

Before updating group membership, read current members, preserve unrelated members, and verify the resulting group. Detect changed revisions or snapshots before writing where supported. A single portal executor does not serialize external administrators: document residual races if the target API lacks conditional writes, block on detected conflicts, and never claim atomic coordination with external tools.

Protect special and externally managed resources. The proposed default namespace is `portal_`, configurable per firewall; writes remain disabled until an administrator explicitly configures the allowed namespace/groups. Existing objects may be referenced with appropriate permission without acquiring portal ownership. Deletion requires authoritative reference checks; incomplete checks block deletion.

## Credentials and audit

Encrypt recoverable credentials at the application field boundary using authenticated encryption from the cryptography library. Provide a versioned key ring through mounted secrets, outside SQLite and source control; new encryption uses the active key and old keys allow controlled rotation. Missing or invalid keys fail closed. Never display stored tokens after saving. Database encryption does not replace access controls or encrypted backup storage.

Audit successful and failed logins, account and role changes, firewall changes, submissions, approval/rejection, execution steps, reconciliation, and scan results. Redact credentials and sensitive payload fields before persistence or logging. Application append-only audit is not tamper-proof against a database administrator; an external protected sink is a deployment option.

## Unused-object assessment

Start with explicit on-demand read-only scans by authorized users. Traverse policy address references and group membership transitively with cycle detection. Handle wildcard references such as `all`, pagination, unsupported constructs, and incomplete reads conservatively. Report `potentially unused` only within the supported scan coverage; show `unknown` when evidence is incomplete. Include scan scope and timestamp, and never treat these alerts as automatic deletion permission.

## Interface

Provide Dashboard, Firewalls/VDOMs, Address Objects, Address Groups, New Request, Approvals, Request Details, History, Unused Objects, and user administration. Use English copy throughout. Show real data and meaningful empty states rather than illustrative counters. Forms show firewall/VDOM scope, object type, proposed changes, and approval/execution state. Request details expose the approved intent, actor identities, step results, and uncertainty without secrets.

Apply a task-focused interface with accessible keyboard navigation, visible focus, labeled inputs, textual status labels, responsive tables, CSRF protection, and server-side authorization for every action. Establish the visual direction separately before UI implementation using the recorded code-first preference.

## Verification and acceptance

- Django checks and migration consistency pass; a clean database migrates successfully.
- Permission tests cover unauthorized scope, disabled accounts, role assignment, and direct service calls.
- Self-approval fails for every role; unapproved, edited, rejected, or cancelled requests cannot execute.
- Lifecycle tests cover duplicate submissions, atomic claims, executor crashes, partial completion, uncertain writes, and reconciliation without replay.
- Credential tests establish ciphertext persistence and log/audit redaction; absent keys fail closed.
- Adapter scenarios cover supported address types, pagination, preserved members, conflicts, rejection, TLS failures, timeouts, and post-write mismatch.
- Usage scans cover nested/cyclic groups, incomplete results, policy references, and unknown classifications.
- Exercise the running application against an HTTP mock of Fortinet, including failures; distinguish simulated evidence from actual device validation.
- Inspect the interface once across desktop and mobile, fix findings together, and perform at most one confirmation pass.

## Deployment boundaries and remaining configuration

Run SQLite on a local persistent volume shared only by the application and single executor; configure busy timeouts and short transactions. Do not scale execution replicas or use network-filesystem SQLite. Back up and restore the database and encryption keys through separately protected procedures. Production requires HTTPS, secure cookies, allowed hosts, trusted proxy settings, explicit secrets, and an IdP configuration if OIDC is enabled.

Exact FortiOS versions, IdP details, credentials, namespace policy, and deployment hostname remain environment inputs. The access presets, read-only approval exemption, on-demand scanning, token authentication, and separate executor are proposed defaults for review. No live firewall mutation is part of initial local verification.
