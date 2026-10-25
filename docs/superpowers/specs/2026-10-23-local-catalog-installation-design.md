# Local catalog and approved firewall installation

Status: approved by the user on 2026-10-23. The user subsequently approved the implementation plan and native execution in the current checkout.

Configuration amendment approved directly by the user on 2026-10-23: firewall connections support HTTP/HTTPS; HTTPS ignores certificate validation errors. Remove Login and per-firewall Allowed groups; label the retained namespace rule Object name prefix, and the credential API Token. These instructions supersede the earlier connection/group-allowlist wording below.

Live-validation amendment on 2026-10-23: the user authorized no required object prefix on their firewall (blank prefix is unrestricted). Live IPv4/group operations were verified only for HTTP 192.168.100.38:80, root VDOM, v7.0.13 build 566. Capability enablement is scoped to that exact endpoint/VDOM/version; it does not enable any version-wide profile.

## Outcome and relationship to the existing specification

Store reusable address objects and address groups in the local database. Authorized users manage this catalog without change requests or approval. Only installation on a firewall or firewall group creates a request requiring independent approval. Provide bulk address creation from CSV upload or pasted CSV text.

This specification supersedes the 2026-10-22 specification where that document treats FortiGate as the source of truth for the catalog, requires approval for local edits, limits requests to one VDOM, or excludes address-group creation. FortiGate remains authoritative for observed device configuration. The local catalog represents desired reusable definitions; it does not prove deployment.

Keep the existing Django, SQLite, templates, HTMX, single executor, audit, encryption, and Fortinet adapter architecture. Application UI and documentation remain in English.

## Catalog and local permissions

Add AddressObject with a unique case-sensitive name, kind, canonical value, revision, creator/updater, and timestamps. Support existing IPv4 host/subnet, FQDN, and wildcard FQDN types and existing name validation. Add AddressGroup with a unique name, revision, actor/timestamp metadata, and explicit membership through AddressObject references. An address object and address group cannot share a name because they occupy a shared device namespace. Nested address groups are outside this increment.

Catalog CRUD, group membership edits, and bulk import are local transactions with audit records and no firewall HTTP calls. Use optimistic revision checks to reject stale edits. Block deletion of objects referenced by local groups; users first remove their memberships. Local deletion never deletes a device resource or submitted request snapshot.

Introduce explicit global catalog_view and catalog_manage grants. Manage includes view; deployment submit/approve grants do not implicitly confer catalog management. Superadministrators administer these grants and may manage the catalog. No existing ordinary user silently receives global catalog visibility through a VDOM grant. Existing firewall/VDOM grants continue to control device access and installation. Catalog readers may select catalog definitions for installation only when also authorized to submit to the destination.

## Bulk creation

Offer CSV upload and a pasted-text field accepting the same CSV format: required header name,kind,value. Include a downloadable example and support UTF-8 with an optional BOM. The preview normalizes each row and reports row-specific errors for malformed fields, invalid names/types/values, duplicate names within the batch, and existing object/group name collisions. Imports create objects only; they do not silently update existing definitions or install anything.

Limit each batch to 1,000 rows and 1 MiB input. Reject unsupported columns and surplus cells instead of guessing. All rows must pass before confirmation. Confirmation revalidates permissions, content, and name uniqueness inside one transaction; any error creates zero objects. Bind confirmation to the previewed content and an import token so repeated confirmation does not duplicate the batch. Expired previews require a new preview. Audit actor, batch ID, count, and created object IDs.

## Firewall groups and destination resolution

Add FirewallGroup with unique name, enabled flag, and explicit members identifying a firewall and one of its enabled VDOMs. A group has at most one selected VDOM per firewall in this increment; the UI labels both firewall and VDOM. This avoids an implicit root VDOM and keeps the requested firewall-group concept distinct from an address group.

Superadministrators manage firewall groups. Ordinary users can select a group only when they have submit permission for every member. Group labels and member lists are visible only to users permitted to view all members. Reject empty groups and disabled scopes at submission. A single-firewall target requires an explicit VDOM selection.

An installation request selects exactly one target type: a single firewall/VDOM or a firewall group. Resolve group members into a fixed, deduplicated destination list at submission. Later group edits do not add or remove destinations from existing requests. Before approval and execution, reject or block revoked permissions and disabled destinations instead of silently skipping them.

## Installation contract and request records

The request form selects local objects and/or address groups, displays automatically included group dependencies, and previews concrete destinations. Persist an immutable snapshot of selected definitions, their revisions, resolved members, destination identifiers and labels, target type, and original firewall-group identity where applicable. Include the complete normalized snapshot in the approval digest. Catalog/group edits after submission cannot alter the approved intent. Preserve snapshots after catalog deletion and protect referenced destination records from hard deletion.

Use a parent installation request for one approval decision and a child installation target for each resolved VDOM. Store execution steps and installed-resource provenance per target. Reuse the existing approval states PENDING, APPROVED, REJECTED, CANCELLED. Target execution states are PENDING, RUNNING, SUCCEEDED, FAILED, RECONCILIATION_REQUIRED. Add PARTIALLY_SUCCEEDED at the parent level.

Submitting requires catalog view and submit access to every destination. One approver must differ from the requester and hold approve access on every destination. Administrative status never bypasses independent approval. Approval covers all destinations as one unit; there is no partial approval. The requester may cancel only while awaiting approval. Idempotency keys bind the requester to the entire immutable installation intent; conflicting reuse is rejected.

Local edits never generate requests. Device operations from this UI are installation only. Remove the old direct device-edit/delete/member-removal submission options from the new-request form. Retain existing requests as historical records, with their original digest, execution path, and independent approval requirements; do not convert or replay them as installations. Remote deletion and removal of unrelated group members are outside this increment.

## Executor behavior and device conflicts

Extend the single leased executor to process installation targets sequentially. Recheck requester and approver activity and destination permissions before each target and before writes. Use short database transactions around claims and state transitions, never across network I/O. Preflight the target's complete snapshot before beginning writes, including names, namespace, protected resources, allowed groups, ownership, capabilities, and dependencies.

Install address dependencies before address groups. If an existing address exactly matches the requested definition, record it as already satisfied without adopting ownership. If it differs, update only a portal-owned address allowed by the configured namespace; otherwise fail with a conflict. Missing addresses are created only within the configured namespace.

For groups, create a missing group only when explicitly permitted by the firewall's allowed-group configuration and a validated group-create capability. For existing allowed groups, add requested members while preserving unrelated members. Installation is additive for group membership: removing a local member does not remove that member from a device. Report both requested membership and observed membership so users can see the distinction. A future destructive synchronization workflow would require a separate explicit specification.

Read back every affected resource and verify the requested address values and member inclusion before recording success. Retain existing TLS, pagination, sanitized error, conflict, and unsupported-version guards. New group-create/update capability profiles remain disabled until the relevant FortiOS contracts are validated. Do not enable real device writes as part of this feature.

Continue to independent targets after a proven target failure. Stop the remaining work within a failed target; record partial steps and retain successful writes. A timeout or ambiguous response marks that target RECONCILIATION_REQUIRED. Other destinations can still run while executor ownership is valid. On lease loss, stop all writes; abandoned running work requires read-only reconciliation, and pending targets are not blindly resumed by a replacement executor. Explicit reconciliation must establish a safe request state before untouched targets continue.

Parent status is RUNNING while processing, RECONCILIATION_REQUIRED if any target is uncertain, SUCCEEDED when all targets succeed, FAILED when all targets fail, and PARTIALLY_SUCCEEDED for a terminal mix of success and failure. Pending work keeps the parent PENDING or RUNNING and is shown explicitly. Reconciliation never sends writes; retrying failed installation intent requires a new approved request. No cross-firewall rollback or atomicity is promised.

## Observations, provenance, and migration

Keep live device inventory and usage scans separate from catalog definitions. Label source, destination, scan time, completeness, and installed snapshot revision. A catalog edit makes an earlier installation older than the current definition; it does not itself establish device drift. Live inventory never silently overwrites the local catalog.

Add catalog, grant, firewall-group, installation-target, snapshot, and per-target provenance schema through additive migrations. Preserve existing ChangeRequest, ExecutionStep, ObjectReference, grants, users, credentials, scans, and audit data. The new catalog starts empty; existing inventory/provenance lacks enough trusted information to manufacture complete local definitions. Users populate the catalog through creation/import. No automatic live-device import is included.

Keep legacy request details/history and executor/reconciliation behavior distinguishable from new installation requests. Update PRODUCT.md, operational documentation, and the execution ledger during implementation to record the new source-of-truth and approval boundaries.

## Interface and service boundaries

Address Objects and Address Groups become local catalog pages with create/edit actions and membership management. Address Objects adds import preview/confirmation. Firewall Administration adds firewall-group management. New Request becomes an installation form. Request Details shows immutable definitions, resolved targets, approval, dependency order, per-target status, and step outcomes. Dashboard/history distinguish local catalog activity from device installations and use real database counts.

Keep parsing/validation, catalog mutations, target resolution/snapshot creation, approval, and per-target execution in focused service modules. Enforce permissions in services as well as views. Reuse Django forms, CSRF, existing audit services, and the Fortinet adapter. No new public JSON API or extra infrastructure is required.

## Acceptance and verification

- Catalog creation, edits, group membership changes, deletion checks, and imports persist after reload and make no firewall calls or change requests.
- Catalog permissions are independent from VDOM grants; unauthorized direct service calls and UI mutations fail.
- Bulk preview reports row errors; invalid batches and confirmation races create nothing; successful batches create all rows once.
- Firewall groups reject duplicate firewalls, incompatible VDOMs, empty targets, disabled members, and unauthorized destinations.
- Submission snapshots include transitive address dependencies, exact revisions, and resolved destinations. Catalog or firewall-group edits cannot mutate them.
- Self-approval, missing destination grants, inactive users, altered digests, unapproved execution, and revoked authorization are rejected.
- Target claims, executor ownership loss, partial results, uncertainty, and reconciliation follow the state rules above.
- HTTP simulation runs the real client/executor for multi-target success, group dependency ordering, matching existing objects, conflicting unowned objects, preserved members, partial failure, and uncertain readback. These checks establish simulated behavior, not live FortiOS compatibility.
- Existing tests continue to pass, including legacy requests, credential redaction, and usage scans. Fresh migrations and upgrade from the existing schema preserve data; Django checks and migration consistency pass.
- Build CSS and inspect changed catalog/import/installation interfaces on desktop and mobile. Document actual checks and remaining environment-dependent limits.

## Review boundary

This document supplies concrete defaults for import format/limits, global catalog grants, explicit VDOM mapping, additive group installation, and retained legacy requests. User review of this written specification precedes the implementation plan. Implementation begins after the plan is reviewed and an execution method is selected, as required by the active brainstorming workflow.
